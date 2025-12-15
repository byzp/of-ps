from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as PlayerAbilityListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.PlayerAbilityListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):

        rsp = PlayerAbilityListRsp_pb2.PlayerAbilityListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(MsgId.PlayerAbilityListRsp, rsp, packet_id)  # 1611,1612
