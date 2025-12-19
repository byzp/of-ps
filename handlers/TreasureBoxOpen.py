from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

import proto.OverField_pb2 as TreasureBoxOpenReq_pb2
import proto.OverField_pb2 as TreasureBoxOpenRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


logger = logging.getLogger(__name__)


@packet_handler(MsgId.TreasureBoxOpenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureBoxOpenReq_pb2.TreasureBoxOpenReq()
        req.ParseFromString(data)

        rsp = TreasureBoxOpenRsp_pb2.TreasureBoxOpenRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # TODO 随机物品生成

        session.send(MsgId.TreasureBoxOpenRsp, rsp, 0)
