from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import EmotionMoonInteractReq, EmotionMoonInteractRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.EmotionMoonInteractReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = EmotionMoonInteractReq()
        req.ParseFromString(data)
        # TODO

        rsp = EmotionMoonInteractRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.info.moon_id = req.emotion_moon_id

        session.send(MsgId.EmotionMoonInteractRsp, rsp, packet_id)
