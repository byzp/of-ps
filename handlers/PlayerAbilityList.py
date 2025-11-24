from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as PlayerAbilityListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(CmdId.PlayerAbilityListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):

        rsp = PlayerAbilityListRsp_pb2.PlayerAbilityListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(CmdId.PlayerAbilityListRsp, rsp, packet_id)  # 1611,1612
