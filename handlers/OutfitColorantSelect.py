from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as OutfitColorantSelectReq_pb2
import proto.OverField_pb2 as OutfitColorantSelectRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 选择服装着色剂 1651 1652
# 硬编码数据响应
"""


@packet_handler(CmdId.OutfitColorantSelectReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitColorantSelectReq_pb2.OutfitColorantSelectReq()
        req.ParseFromString(data)

        rsp = OutfitColorantSelectRsp_pb2.OutfitColorantSelectRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # 硬编码数据
        rsp.param.picture_id = 3
        rsp.param.uvy = 0.0
        rsp.param.is_dye = False

        # 添加参数数组
        params_values = [
            0.22,
            0.06,
            0.94,
            0.12,
            0.2,
            0.19,
            0.88,
            0.76,
            0.44,
            0.76,
            -0.51,
            0.82,
            0.83,
            0.14,
            0.13,
            0.62,
            0.73,
            0.5,
            -0.61,
            0.46,
            0.23,
            0.95,
            0.29,
            0.29,
            0.16,
            0.69,
            0.22,
            0.87,
            0.53,
            0.39,
            -0.11,
            0.88,
            0.68,
            0.94,
            -0.48,
            0.23,
            0.04,
            0.92,
            -0.11,
            0.77,
            0.05,
            0.71,
            0.88,
            0.38,
            0.97,
            0.07,
            -0.77,
            0.88,
            0.91,
            0.2,
            0.98,
            0.66,
            0.23,
            0.45,
            0.37,
            0.64,
            0.0,
            0.73,
            -0.73,
            0.08,
            0.29,
            0.72,
            0.24,
            0.17,
        ]

        # 将参数添加到params数组
        for value in params_values:
            rsp.param.params.append(value)

        session.send(CmdId.OutfitColorantSelectRsp, rsp, False, packet_id)
