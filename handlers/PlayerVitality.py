from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as PlayerVitalityReq_pb2
import proto.OverField_pb2 as PlayerVitalityRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.PlayerVitalityReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerVitalityReq_pb2.PlayerVitalityReq()
        req.ParseFromString(data)

        rsp = PlayerVitalityRsp_pb2.PlayerVitalityRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.vitality_buy_num = TEST_DATA["parsed_result"]["vitality_buy_num"]
        # items is empty as specified in the requirements

        session.send(CmdId.PlayerVitalityRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"parsed_result": {"status": 1, "vitality_buy_num": 0, "items": []}}
