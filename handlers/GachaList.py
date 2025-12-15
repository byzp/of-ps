from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as Gacha_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin


@packet_handler(MsgId.GachaListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = Gacha_pb2.GachaListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(MsgId.GachaListRsp, rsp, packet_id)  # 1443,1444
        # session.sbin(1444, bin["1444"],  packet_id)
