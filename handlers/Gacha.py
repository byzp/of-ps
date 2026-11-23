from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random

from proto.net_pb2 import (
    GachaReq,
    GachaRsp,
    StatusCode,
    PackNotice,
    ItemDetail,
)
from config import Config
from utils.res_loader import res
import utils.db as db
from utils import item_mgr
from utils.pb_create import make_item
from utils import achieve_track


@packet_handler(MsgId.GachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaReq()
        req.ParseFromString(data)

        with achieve_track.batch(session):
            self._draw(session, req, packet_id)

    def _draw(self, session, req, packet_id):

        rsp = GachaRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.info.gacha_id = req.gacha_id
        rsp.info.gacha_times = 1 if req.is_single else 10
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        gt = db.get_gacha_guarantee(session.player_id, req.gacha_id)
        _gt_cap = next(
            (
                int(e.get("max_times") or 70)
                for e in res["Gacha"]["info"]["datas"]
                if isinstance(e, dict) and e.get("i_d") == req.gacha_id
            ),
            70,
        )
        _pool_found = False
        for i in res["Gacha"]["pool"]["datas"]:
            if i["i_d"] == req.gacha_id:
                _pool_found = True
                pools = []
                for i2 in i["items"]:
                    pools.append(i2["free_gacha_pool_i_d"])
                rewards = []
                rewards_gt = []
                gt_pool = 0
                for i2 in res["Gacha"]["info"]["datas"]:
                    if i2["i_d"] == req.gacha_id:
                        # 单抽走 consume_item1(招募券), 十连走 consume_item2(星石)
                        if req.is_single:
                            cost_id = i2.get("consume_item1_i_d", 0)
                            cost_num = int(i2.get("method1_count", 0) or 0) * int(
                                i2.get("consume_item1_num", 1) or 1
                            )
                        else:
                            cost_id = i2.get("consume_item2_i_d", 0)
                            cost_num = int(i2.get("consume_item2_num", 0) or 0)
                        if not cost_id or cost_num <= 0:
                            break
                        consume_b = db.get_item_detail(session.player_id, cost_id)
                        if not consume_b:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            session.send(MsgId.GachaRsp, rsp, packet_id)
                            return
                        item = rsp1.items.add()
                        item.ParseFromString(consume_b)
                        item.main_item.base_item.num -= cost_num
                        if item.main_item.base_item.num < 0:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            session.send(MsgId.GachaRsp, rsp, packet_id)
                            return
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            item.main_item.item_id,
                        )
                        gt_pool = i2.get("big_guarantee_pool_i_d", 0)
                        break
                for i2 in res["Gacha"]["reward_pool"]["datas"]:
                    if i2["i_d"] in pools:
                        for i3 in i2["items"]:
                            rewards.append(i3["item_i_d"])
                    if i2["i_d"] == gt_pool:
                        for i3 in i2["items"]:
                            rewards_gt.append(i3["item_i_d"])
        if not _pool_found or not rewards:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GachaRsp, rsp, packet_id)
            return
        for _ in range(10):
            if rewards_gt and gt + 1 >= _gt_cap:
                r = random.choice(rewards_gt)
                gt = 0
            else:
                r = random.choice(rewards)
                gt += 1
            if (
                not Config.SKIP_QUESTS
                and req.gacha_id == 2000
                and req.is_single
                and db.get_total_gacha_num(session.player_id, 2000) == 0
            ):
                r = 102001
            c = False
            for i in res["Character"]["character"]["datas"]:
                if i["i_d"] == r:
                    item = rsp.items.add()
                    # 重复角色自动转换为碎片(repeat_item_i_d)
                    dup = item_mgr.grant_character(
                        session.player_id, r, item, pack_notice=rsp1
                    )
                    if not dup:
                        extra = ItemDetail()
                        make_item(107, 500, session.player_id, extra)
                        item.extras.add().CopyFrom(extra.main_item)
                        item_mgr.grant_items(
                            session.player_id,
                            [(107, 500)],
                            pack_notice=rsp1,
                            session=session,
                        )
                        for i2 in res["Item"]["item"]["datas"]:
                            if i2["i_d"] == item.main_item.item_id:
                                item.extra_quality = i2.get("quality", 0)
                                break
                    c = True
                    break
            if not c:
                item_mgr.grant_single_item(
                    session.player_id,
                    r,
                    num=1,
                    rsp_items=rsp.items,
                    pack_notice=rsp1,
                )
            else:
                rsp1.items.add().CopyFrom(item)
            db.add_gacha_record(session.player_id, req.gacha_id, r)
            if req.is_single:
                break
        db.set_gacha_guarantee(session.player_id, req.gacha_id, gt)

        if gt_pool:
            rsp.info.guarantee = max(0, _gt_cap - gt)
        session.send(MsgId.GachaRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
        achieve_track.report(session, "gacha", amount=1 if req.is_single else 10)
