import pickle
import random
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    EBagItemTag,
    ItemUseReq,
    ItemUseRsp,
    ItemDetail,
    PackNotice,
    PlayerBuffNotice as _PBN,
    StatusCode,
)
import utils.db as db
from utils import achieve_track
from utils import item_mgr
from utils.res_loader import res


@packet_handler(MsgId.ItemUseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # 一次使用动作只构造一份成就帧(eat/stamina/gain 多路计数合并)
        with achieve_track.batch(session):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = ItemUseReq()
        req.ParseFromString(data)

        rsp = ItemUseRsp()
        rsp.dungeon_id = session.dungeon[0] if session.dungeon else 0
        rsp.status = StatusCode.StatusCode_OK

        item = db.get_item_detail(session.player_id, req.item_id)
        if not item:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.ItemUseRsp, rsp, packet_id)
            return
        else:
            item_use = ItemDetail()
            item_use.ParseFromString(item)
            if item_use.main_item.base_item.num >= req.num:
                item_use.main_item.base_item.num -= req.num
                rsp1 = PackNotice()
                rsp1.status = StatusCode.StatusCode_OK
                rsp1.items.add().CopyFrom(item_use)
                db.set_item_detail(
                    session.player_id, item_use.SerializeToString(), req.item_id, None
                )
            else:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.ItemUseRsp, rsp, packet_id)
                return

        # 成就: 吃任意食物75(Item.new_bag_item_tag==EBagItemTag_Food);
        # 使用体力/精力药剂计入消耗(80/81)
        _tag = next(
            (
                e.get("new_bag_item_tag")
                for e in res["Item"]["item"]["datas"]
                if isinstance(e, dict) and e.get("i_d") == req.item_id
            ),
            None,
        )
        if _tag == EBagItemTag.EBagItemTag_Food:
            achieve_track.report(session, "eat_food", amount=req.num)
            # 料理效果(Cooking.cook_affect): 推送 LIFE 类 Buff 并持久化到期时间

            _affect = next(
                (
                    a
                    for a in res["Cooking"]["cook_affect"]["datas"]
                    if isinstance(a, dict) and a.get("i_d") == req.item_id
                ),
                None,
            )
            if _affect and _affect.get("buff_i_d"):
                _buff_id = int(_affect["buff_i_d"])
                _dur = int(_affect.get("food_effect_type_param", 0) or 0)
                _end = int(time.time()) + _dur
                _raw = db.get_kv(session.player_id, "buffs", "life", b"")
                _store = pickle.loads(_raw) if _raw else {}
                _store[_buff_id] = max(_end, int(_store.get(_buff_id, 0)))
                db.set_kv(session.player_id, "buffs", "life", pickle.dumps(_store))

                _n = _PBN()
                _n.status = StatusCode.StatusCode_OK
                _pb = _n.player_buffs.add()
                _pb.system_type = 2  # BuffSystemType_LIFE
                _b = _pb.buff_lst.add()
                _b.buff_id = _buff_id
                _b.end_time = _end
                session.send(MsgId.PlayerBuffNotice, _n, 0)
        elif req.item_id == 10:
            achieve_track.report(session, "stamina_drink", amount=req.num)
        elif req.item_id == 11:
            achieve_track.report(session, "energy_drink", amount=req.num)

        if _tag == 32:
            _relate = next(
                (
                    e.get("relate_i_d", 0)
                    for e in res["Item"]["item"]["datas"]
                    if isinstance(e, dict) and e.get("i_d") == req.item_id
                ),
                0,
            )
            if _relate and req.num > 0:
                item_mgr.grant_items(
                    session.player_id,
                    [(10, int(_relate) * req.num)],
                    pack_notice=rsp1,
                    rsp_items=rsp.items,
                    session=session,
                )
                achieve_track.report(session, "vitality_restore", amount=req.num)
        elif _tag == 35:
            _relate = next(
                (
                    e.get("relate_i_d", 0)
                    for e in res["Item"]["item"]["datas"]
                    if isinstance(e, dict) and e.get("i_d") == req.item_id
                ),
                0,
            )
            if _relate and req.num > 0:
                item_mgr.grant_items(
                    session.player_id,
                    [(11, int(_relate) * req.num)],
                    pack_notice=rsp1,
                    rsp_items=rsp.items,
                    session=session,
                )
                achieve_track.report(session, "energy_restore", amount=req.num)

        # 互动道具(Expression.catcher: need_item_i_d -> action_i_d,
        # new_bag_item_tag=55): 使用后解锁动作(24h, 与 ActionStudy 同存储)
        catcher = next(
            (
                e
                for e in res["Expression"]["catcher"]["datas"]
                if isinstance(e, dict) and e.get("need_item_i_d") == req.item_id
            ),
            None,
        )
        if catcher:

            expire_ms = int((time.time() + 24 * 3600) * 1000)
            raw = db.get_kv(session.player_id, "actions", "ids", b"")
            actions = {}
            for pair in raw.decode().split(","):
                if ":" in pair:
                    aid, exp = pair.split(":")
                    actions[int(aid)] = int(exp)
            actions[catcher["action_i_d"]] = max(
                actions.get(catcher["action_i_d"], 0), expire_ms
            )
            db.set_kv(
                session.player_id,
                "actions",
                "ids",
                ",".join(f"{k}:{v}" for k, v in actions.items()).encode(),
            )
            achieve_track.report(session, "use_interact_item")

        for data in res.get("Reward", {}).get("reward_pool", {}).get("datas", []):
            if data["i_d"] == req.item_id:
                # 奖励发放走实例安全入口(武器/映像等实例类单独落库)
                rp = []
                for reward_pool in data["reward_pool_group"]:
                    rp.append(reward_pool["reward_pool_group_i_d"])
                for item_pool in (
                    res.get("Reward", {}).get("reward_item_pool", {}).get("datas", [])
                ):
                    if item_pool["i_d"] in rp:
                        for item in item_pool["reward_item_pool_group"]:
                            r_num = random.randint(
                                item["item_min_count"], item["item_max_count"]
                            )
                            item_mgr.grant_single_item(
                                session.player_id,
                                item["item_i_d"],
                                num=r_num,
                                pack_notice=rsp1,
                                rsp_items=rsp.items,
                            )
        session.send(
            MsgId.ItemUseRsp, rsp, packet_id
        )  # 一些测试物品可能没有奖励池,不能放到循环内
        session.send(MsgId.PackNotice, rsp1, 0)
