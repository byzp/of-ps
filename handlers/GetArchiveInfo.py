from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GetArchiveInfoReq, GetArchiveInfoRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetArchiveInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetArchiveInfoReq()
        req.ParseFromString(data)

        rsp = GetArchiveInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        match req.key:
            case "BlessingTreeTutotal":
                rsp.value = "1"
            case "FixOrFlolowMode":
                pass
            case "":
                rsp.value = "5/31/2025"
            case "ButtonModeState":
                pass
            case _:
                rsp.value = "已显示"
        session.send(MsgId.GetArchiveInfoRsp, rsp, packet_id)  # 1213,1214
