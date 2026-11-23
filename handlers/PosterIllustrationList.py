from proto.net_pb2 import ItemDetail

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PosterIllustrationListRsp,
    PosterIllustrationListReq,
    StatusCode,
    RewardStatus,
    EBagItemTag,
)
import utils.db as db
from utils.res_loader import res

"""
# 映像图鉴列表 1423 1424
图鉴条目 = Poster.poster_illustration(is_show);
已获得 = 背包持有对应映像实例(poster.poster_id -> poster.illustration_i_d)。
status: 已获得=Reward, 未获得=NotReward。
"""


@packet_handler(MsgId.PosterIllustrationListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = PosterIllustrationListRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 持有的映像 id 集合
        owned = set()
        for blob in db.get_item_detail(session.player_id, table="items_s"):

            d = ItemDetail()
            d.ParseFromString(blob)
            if d.main_item.item_tag == EBagItemTag.EBagItemTag_Poster:
                owned.add(d.main_item.poster.poster_id)

        # poster_id -> illustration_i_d
        ill_of = {}
        for row in res["Poster"]["poster"]["datas"]:
            if isinstance(row, dict) and row.get("illustration_i_d"):
                ill_of[row["item_i_d"]] = row["illustration_i_d"]

        claimed = {
            int(k) for k in db.get_claimed(session.player_id, "poster_illustration")
        }
        owned_ids = {ill_of[p] for p in owned if p in ill_of}
        for row in res["Poster"]["poster_illustration"]["datas"]:
            if not isinstance(row, dict) or not row.get("is_show"):
                continue
            if row["i_d"] not in owned_ids and row["i_d"] not in claimed:
                continue  # 新号回空列表，不将所有未获得映像伪装成已登记条目。
            entry = rsp.poster_illustrations.add()
            entry.poster_illustration_id = row["i_d"]
            if row["i_d"] in claimed or row["i_d"] in owned_ids:
                entry.status = RewardStatus.Reward
            else:
                entry.status = RewardStatus.NotReward

        session.send(MsgId.PosterIllustrationListRsp, rsp, packet_id)  # 1423,1424
