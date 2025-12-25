from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as AbilityBadgeListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.AbilityBadgeListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = AbilityBadgeListRsp_pb2.AbilityBadgeListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO
        session.send(MsgId.AbilityBadgeListRsp, rsp, packet_id)  # 1631,1632
