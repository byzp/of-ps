from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as SetArchiveInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin


@packet_handler(CmdId.SetArchiveInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SetArchiveInfoRsp_pb2.SetArchiveInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO
        session.send(CmdId.SetArchiveInfoRsp, rsp, False, packet_id)  # 1211,1212
