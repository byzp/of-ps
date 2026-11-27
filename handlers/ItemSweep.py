from config import Config
from utils import achieve_track

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ItemSweepReq, ItemSweepRsp, StatusCode, PackNotice

import utils.db as db
from utils.res_loader import res
from utils import item_mgr


def _quick_cfg(item_id, player_level):
    """QuickObtaining.json quick_obtaining: 按物品 id 查速刷条目,
    quick_obtaining_item 按 player_level 分档, 取 <= 玩家等级的最高档。
    返回 {"num": 单次获得数量, "need_vitality": 单次体力消耗} 或 None。"""
    for e in res.get("QuickObtaining", {}).get("quick_obtaining", {}).get("datas", ()):
        if e.get("i_d") != item_id:
            continue
        picked = None
        for g in e.get("quick_obtaining_item", ()):
            lv = g.get("player_level", 1)
            if lv <= player_level and (
                picked is None or lv > picked.get("player_level", 1)
            ):
                picked = g
        if picked is None and e.get("quick_obtaining_item"):
            picked = e["quick_obtaining_item"][0]  # 低于最低档时按最低档
        return picked
    return None


@packet_handler(MsgId.ItemSweepReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ItemSweepReq()
        req.ParseFromString(data)

        rsp = ItemSweepRsp()
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        if not req.item_id or req.count <= 0:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ItemSweepRsp, rsp, packet_id)
            return
        try:
            count = item_mgr.validate_count(req.count, label="sweep count")
            player_level = db.get_players_info(session.player_id, "level")[0]
            cfg = _quick_cfg(req.item_id, player_level)
            if not cfg:
                raise item_mgr.EconomyConfigError("missing quick obtaining config")
            per_round = item_mgr.validate_count(cfg.get("num", 0), label="sweep yield")
            if count % per_round:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.ItemSweepRsp, rsp, packet_id)
                return
            rounds = count // per_round
            gain = item_mgr.checked_mul(per_round, rounds)
            vitality = item_mgr.validate_count(
                cfg.get("need_vitality", 0), allow_zero=True, label="sweep vitality"
            )
            cost = item_mgr.checked_mul(vitality, rounds) if vitality else 0
            gain_exp = (
                item_mgr.checked_mul(cost, Config.EXP_PER_VITALITY) if cost else 0
            )
            item_mgr.validate_stackable_item_id(req.item_id)
            item_mgr.validate_stackable_item_id(Config.VITALITY_ITEM_ID)
            reward_list = [(req.item_id, gain)]
            if gain_exp > 0:
                reward_list.append((1, gain_exp))
            item_mgr.validate_rewards(reward_list)

            if not req.is_sweep:
                tmp = rsp.rewards.add()
                tmp.main_item.item_id = req.item_id
                tmp.main_item.base_item.item_id = req.item_id
                tmp.main_item.base_item.num = gain
                rsp.status = StatusCode.StatusCode_OK
            else:
                with item_mgr.player_lock(session.player_id), item_mgr.deferred_notifications(), db.transaction():
                    if cost and not item_mgr.consume_items(
                        session.player_id,
                        [(Config.VITALITY_ITEM_ID, cost)],
                        pack_notice=notice,
                        session=session,
                    ):
                        rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    else:
                        item_mgr.grant_items(
                            session.player_id,
                            reward_list,
                            rsp_items=rsp.rewards,
                            pack_notice=notice,
                            session=session,
                        )
                        rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.rewards[:]
            del notice.items[:]

        session.send(MsgId.ItemSweepRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and notice.items:
            session.send(MsgId.PackNotice, notice, 0)
