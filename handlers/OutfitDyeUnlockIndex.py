from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    OutfitDyeUnlockIndexReq,
    OutfitDyeUnlockIndexRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db
from utils.trace import trace
from utils import item_mgr

"""
# 解锁时装染色方案槽位 1645 1646
解锁状态持久化在时装 ItemDetail.main_item.outfit.dye_schemes[index].is_un_lock
(OutFitDyeSave 对 dye_schemes 按下标访问, 这里保持同样的下标语义)
"""


@packet_handler(MsgId.OutfitDyeUnlockIndexReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitDyeUnlockIndexReq()
        req.ParseFromString(data)

        rsp = OutfitDyeUnlockIndexRsp()

        if req.index >= Config.MAX_DYE_SCHEME_NUM:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.OutfitDyeUnlockIndexRsp, rsp, packet_id)
            return

        if not req.outfit_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.OutfitDyeUnlockIndexRsp, rsp, packet_id)
            return
        item_b = db.get_item_detail(session.player_id, req.outfit_id)
        if not item_b:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.OutfitDyeUnlockIndexRsp, rsp, packet_id)
            return

        outfit = ItemDetail()
        outfit.ParseFromString(item_b)
        schemes = outfit.main_item.outfit.dye_schemes
        while len(schemes) <= req.index:
            scheme = schemes.add()
            scheme.scheme_index = len(schemes) - 1
        schemes[req.index].is_un_lock = True
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if not item_mgr.consume_items(
            session.player_id,
            [(102, 100)],
            pack_notice=pack,
            session=session,
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.OutfitDyeUnlockIndexRsp, rsp, packet_id)  # 1645,1646
            return
        db.set_item_detail(session.player_id, outfit.SerializeToString(), req.outfit_id)
        pack.items.add().CopyFrom(outfit)

        rsp.status = StatusCode.StatusCode_OK
        trace("dye_unlock", player=session.player_id, outfit=req.outfit_id,
              index=req.index, status=rsp.status)
        session.send(MsgId.OutfitDyeUnlockIndexRsp, rsp, packet_id)  # 1645,1646
        session.send(MsgId.PackNotice, pack, 0)
