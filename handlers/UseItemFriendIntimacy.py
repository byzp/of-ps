from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    UseItemFriendIntimacyReq,
    UseItemFriendIntimacyRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)
import utils.db as db
from utils.res_loader import res
import time
from utils import refresh

"""
# 好友亲密度道具 2651 2652
Item.relate_i_d = 增加的亲密度(1501/1502/1503 -> 5/10/20);
GlobalConfig: IntimacyMax=99999 总上限, IntimacyGiftMaxUseNumber=999 每日赠送次数上限,
IntimacyLevelUnLockGift=1 亲密度等级>=1(即已是好友)才可赠送。
每日赠送计数持久化于 kv(ns=intimacy, key=<日期>:<好友id>)。
"""


def _gift_daily_cap():
    for e in res["GlobalConfig"]["config"]["datas"]:
        if e.get("key") == "IntimacyGiftMaxUseNumber":
            return int(e["values"][0])
    return 999


@packet_handler(MsgId.UseItemFriendIntimacyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UseItemFriendIntimacyReq()
        req.ParseFromString(data)

        rsp = UseItemFriendIntimacyRsp()
        rsp.friend_id = req.friend_id

        # 道具配置(new_bag_item_tag=45 亲密度道具, relate_i_d=增加值)
        cfg = next(
            (
                e
                for e in res["Item"]["item"]["datas"]
                if isinstance(e, dict) and e.get("i_d") == req.item_id
            ),
            None,
        )
        increase = int(cfg.get("relate_i_d", 0)) if cfg else 0
        item_data = db.get_item_detail(session.player_id, req.item_id)
        if not cfg or not increase or not item_data:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            rsp.intimacy = 0
            session.send(MsgId.UseItemFriendIntimacyRsp, rsp, packet_id)
            return

        # 双向好友关系校验
        friend_row = db.get_friend_info(
            session.player_id, req.friend_id, "friend_intimacy"
        )
        if not friend_row:
            rsp.status = StatusCode.StatusCode_FRIEND_NOT_EXIST
            rsp.intimacy = 0
            session.send(MsgId.UseItemFriendIntimacyRsp, rsp, packet_id)
            return
        current_intimacy = friend_row[0]

        # 每日赠送次数(IntimacyGiftMaxUseNumber)
        day_key = f"{refresh.day_index()}:{req.friend_id}"
        used = int(db.get_kv(session.player_id, "intimacy", day_key, 0) or 0)
        cap = _gift_daily_cap()
        if used >= cap:
            rsp.status = StatusCode.StatusCode_FRIEND_INTIMACY_DAY_GIFT_LIMIT
            rsp.intimacy = current_intimacy
            session.send(MsgId.UseItemFriendIntimacyRsp, rsp, packet_id)
            return

        # 扣道具
        item = ItemDetail()
        item.ParseFromString(item_data)
        if item.main_item.base_item.num < 1:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            rsp.intimacy = current_intimacy
            session.send(MsgId.UseItemFriendIntimacyRsp, rsp, packet_id)
            return
        item.main_item.base_item.num -= 1
        db.set_item_detail(
            session.player_id, item.SerializeToString(), req.item_id, None
        )

        # 亲密度双向同步, IntimacyMax 封顶
        intimacy_max = 99999
        for e in res["GlobalConfig"]["config"]["datas"]:
            if e.get("key") == "IntimacyMax":
                intimacy_max = int(e["values"][0])
                break
        if current_intimacy >= intimacy_max:
            rsp.status = StatusCode.StatusCode_FRIEND_INTIMACY_LIMIT
            rsp.intimacy = current_intimacy
            session.send(MsgId.UseItemFriendIntimacyRsp, rsp, packet_id)
            return
        new_intimacy = min(current_intimacy + increase, intimacy_max)
        db.set_friend_info(
            session.player_id, req.friend_id, "friend_intimacy", new_intimacy
        )
        db.set_friend_info(
            req.friend_id, session.player_id, "friend_intimacy", new_intimacy
        )
        db.set_kv(session.player_id, "intimacy", day_key, used + 1)

        rsp.status = StatusCode.StatusCode_OK
        rsp.intimacy = new_intimacy
        session.send(
            MsgId.UseItemFriendIntimacyRsp, rsp, packet_id
        )  # 2651 2652 使用道具增加好友亲密度

        # 数量更新通知
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        pack.items.add().CopyFrom(item)
        session.send(MsgId.PackNotice, pack, packet_id)
