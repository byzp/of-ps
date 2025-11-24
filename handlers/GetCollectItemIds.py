from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as GetCollectItemIdsRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin


@packet_handler(CmdId.GetCollectItemIdsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetCollectItemIdsRsp_pb2.GetCollectItemIdsRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # session.send(CmdId.GetCollectItemIdsRsp, rsp) #1997,1998
        session.sbin(1998, bin["1998"], packet_id)
