from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as GetMailsRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin


@packet_handler(MsgId.GetMailsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):

        rsp = GetMailsRsp_pb2.GetMailsRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # session.send(MsgId.GetMailsRsp, rsp) #1121,1122
        session.sbin(1122, bin["1122"], packet_id)
