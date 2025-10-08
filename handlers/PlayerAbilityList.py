from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as PlayerAbilityListReq_pb2
import proto.OverField_pb2 as PlayerAbilityListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

@packet_handler(CmdId.PlayerAbilityListReq)
class PlayerAbilityListHandler(PacketHandler):
    def handle(self, session, data: bytes):
        
        rsp = PlayerAbilityListRsp_pb2.PlayerAbilityListRsp()
        rsp.status = StatusCode_pb2.StatusCode_Ok

        session.send(CmdId.PlayerAbilityListRsp, rsp)
