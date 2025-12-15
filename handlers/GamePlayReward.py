from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging


import proto.OverField_pb2 as GamePlayRewardReq_pb2
import proto.OverField_pb2 as GamePlayRewardRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GamePlayRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):

        req = GamePlayRewardReq_pb2.GamePlayRewardReq()
        req.ParseFromString(data)

        rsp = GamePlayRewardRsp_pb2.GamePlayRewardRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(MsgId.GamePlayRewardRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"parsed_result": {"status": 1}}
