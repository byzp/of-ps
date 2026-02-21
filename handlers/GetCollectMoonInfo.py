from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GetCollectMoonInfoReq, GetCollectMoonInfoRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetCollectMoonInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCollectMoonInfoReq()
        req.ParseFromString(data)

        rsp = GetCollectMoonInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scene_id = req.scene_id
        # TODO
        session.send(MsgId.GetCollectMoonInfoRsp, rsp, packet_id)
