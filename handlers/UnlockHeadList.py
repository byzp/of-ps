from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UnlockHeadListReq_pb2
import proto.OverField_pb2 as UnlockHeadListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
获取已解锁头像列表 1529 1530
"""

@packet_handler(CmdId.UnlockHeadListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UnlockHeadListReq_pb2.UnlockHeadListReq()
        req.ParseFromString(data)

        rsp = UnlockHeadListRsp_pb2.UnlockHeadListRsp()
        
        # Set status from test data
        rsp.status = TEST_DATA["status"]
        
        # Add heads from test data
        rsp.heads.extend(TEST_DATA["heads"])

        session.send(CmdId.UnlockHeadListRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "heads": [
        41101,
        41102,
        41103,
        41104,
        41201,
        41202,
        41302,
        42101,
        42102,
        42201,
        42204,
        43102,
        43104,
        43202,
        43203,
        44101,
        44102,
        44103,
        44104,
        44202,
        44203,
        44301,
        44302,
        9003,
        9004,
        9011,
        9012,
        9013,
        9014,
        9015,
        9016,
        9017,
        9018,
        9019,
        9020,
        9101,
        9108,
        9110,
        9112,
        9114,
        9115,
        9118,
        9119,
        9124,
        9130,
        9131,
        9134,
        9142,
        9150,
        9301,
        9302,
        9303,
        9306,
        9307,
        9308,
        9310,
        9317,
        9318,
        9319,
        9324,
        9328,
        9336,
        9338,
        9339,
        9340,
        9358,
        9360,
    ]
}