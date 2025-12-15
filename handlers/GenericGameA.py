from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GenericGameAReq_pb2
import proto.OverField_pb2 as GenericGameARsp_pb2

logger = logging.getLogger(__name__)


"""
# 通用游戏消息A 2301 2302
"""


@packet_handler(MsgId.GenericGameAReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericGameAReq_pb2.GenericGameAReq()
        req.ParseFromString(data)

        rsp = GenericGameARsp_pb2.GenericGameARsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.generic_msg_id = TEST_DATA["generic_msg_id"]

        # Add params from test data
        for param_data in TEST_DATA["params"]:
            param = rsp.params.add()
            param.param_type = param_data["param_type"]
            param.int_value = param_data["int_value"]
            param.float_value = param_data["float_value"]
            param.double_value = param_data["double_value"]
            param.bool_value = param_data["bool_value"]
            param.string_value = param_data["string_value"]

        session.send(MsgId.GenericGameARsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "generic_msg_id": 0,
    "params": [
        {
            "param_type": 0,
            "int_value": 0,
            "float_value": 0.0,
            "double_value": 0.0,
            "bool_value": False,
            "string_value": "",
        }
    ],
}
