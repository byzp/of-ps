from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as Gacha_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin


@packet_handler(CmdId.GachaListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = Gacha_pb2.GachaListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(CmdId.GachaListRsp, rsp, True, packet_id)  # 1443,1444
        # session.sbin(1444, bin["1444"], False, packet_id)
