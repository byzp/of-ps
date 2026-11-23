from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetArchiveInfoReq, GetArchiveInfoRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.GetArchiveInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetArchiveInfoReq()
        req.ParseFromString(data)

        rsp = GetArchiveInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        stored = db.get_kv(session.player_id, "archive", req.key)
        if stored is not None:
            rsp.value = str(stored)
        elif req.key == "BlessingTreeTutotal":
            rsp.value = "1"
        session.send(MsgId.GetArchiveInfoRsp, rsp, packet_id)  # 1213,1214
