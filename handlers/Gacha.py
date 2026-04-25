from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random

from proto.net_pb2 import (
    GachaReq,
    GachaRsp,
    StatusCode,
    PackNotice,
    QuestNotice,
    QuestStatus,
)
from config import Config
from utils.res_loader import res
import utils.db as db
from utils.pb_create import make_item


@packet_handler(MsgId.GachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaReq()
        req.ParseFromString(data)

        rsp = GachaRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.info.gacha_id = req.gacha_id
        rsp.info.gacha_times = 1 if req.is_single else 10
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        gt = db.get_gacha_guarantee(session.player_id, req.gacha_id)
        for i in res["Gacha"]["pool"]["datas"]:
            if i["i_d"] == req.gacha_id:
                pools = []
                for i2 in i["items"]:
                    pools.append(i2["free_gacha_pool_i_d"])
                rewards = []
                rewards_gt = []
                gt_pool = 0
                for i2 in res["Gacha"]["info"]["datas"]:
                    if i2["i_d"] == req.gacha_id:
                        consume_b = db.get_item_detail(
                            session.player_id, i2["consume_item2_i_d"]
                        )
                        if not consume_b:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            session.send(MsgId.GachaRsp, rsp, packet_id)
                            return
                        item = rsp1.items.add()
                        item.ParseFromString(consume_b)
                        item.main_item.base_item.num -= rsp.info.gacha_times
                        if item.main_item.base_item.num < 0:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            session.send(MsgId.GachaRsp, rsp, packet_id)
                            return
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            item.main_item.item_id,
                        )
                        gt_pool = i2["big_guarantee_pool_i_d"]
                        break
                for i2 in res["Gacha"]["reward_pool"]["datas"]:
                    if i2["i_d"] in pools:
                        for i3 in i2["items"]:
                            rewards.append(i3["item_i_d"])
                    if i2["i_d"] == gt_pool:
                        for i3 in i2["items"]:
                            rewards_gt.append(i3["item_i_d"])
        for _ in range(10):
            if gt >= 70:
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
                rsp2 = QuestNotice()
                rsp2.status = StatusCode.StatusCode_OK
                tmp = rsp2.quests.add()
                # 主线的抽卡引导任务
                tmp.ParseFromString(db.get_quest(session.player_id, 100013))
                for ii in tmp.conditions:
                    ii.status = QuestStatus.QuestStatus_Finish
                    db.set_quest(
                        session.player_id,
                        tmp.quest_id,
                        tmp.SerializeToString(),
                    )
                tmp.status = QuestStatus.QuestStatus_Finish
                session.send(MsgId.QuestNotice, rsp2, 0)

            c = False
            item = rsp.items.add()
            for i in res["Character"]["character"]["datas"]:
                if i["i_d"] == r:
                    item.main_item.item_id = r
                    db.add_character(
                        session.player_id, r, item.main_item.character
                    )  # TODO 重复角色转换
                    c = True
                    for i in res["Item"]["item"]["datas"]:
                        if i["i_d"] == r:
                            item.extra_quality = i.get("quality", 0)
                    break
            if not c:
                make_item(r, 1, session.player_id, item)
                db.set_item_detail(
                    session.player_id,
                    item.SerializeToString(),
                    None,
                    item.main_item.poster.instance_id,
                )  # TODO 服装池
            rsp1.items.add().CopyFrom(item)
            db.add_gacha_record(session.player_id, req.gacha_id, r)
            if req.is_single:
                break
        db.set_gacha_guarantee(session.player_id, req.gacha_id, gt)

        rsp.info.guarantee = 70 - gt
        session.send(MsgId.GachaRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
