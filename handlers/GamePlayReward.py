from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging


from proto.net_pb2 import GamePlayRewardReq, GamePlayRewardRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GamePlayRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):

        req = GamePlayRewardReq()
        req.ParseFromString(data)

        rsp = GamePlayRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.GamePlayRewardRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"parsed_result": {"status": 1}}
