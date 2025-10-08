from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as Gacha_pb2
import proto.OverField_pb2 as StatusCode_pb2

@packet_handler(CmdId.GachaListReq)
class GachaListHandler(PacketHandler):
    def handle(self, session, data: bytes):
        rsp = Gacha_pb2.GachaListRsp()
        rsp.status = StatusCode_pb2.StatusCode_Ok

        session.send(CmdId.GachaListRsp, rsp)
        