from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import SetArchiveInfoReq, SetArchiveInfoRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.SetArchiveInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SetArchiveInfoReq()
        req.ParseFromString(data)

        # 档案键值持久化于 kv ns=archive(GetArchiveInfo 读同一处)
        db.set_kv(session.player_id, "archive", req.key, req.value)

        rsp = SetArchiveInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.key = req.key
        rsp.value = req.value
        session.send(MsgId.SetArchiveInfoRsp, rsp, packet_id)  # 1211,1212
