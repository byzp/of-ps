from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import CollectMoonReq, CollectMoonRsp, StatusCode


logger = logging.getLogger(__name__)


@packet_handler(MsgId.CollectMoonReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectMoonReq()
        req.ParseFromString(data)

        rsp = CollectMoonRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.moon_id = req.moon_id
        # TODO items

        session.send(MsgId.CollectMoonRsp, rsp, packet_id)
