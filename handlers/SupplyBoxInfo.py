from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import proto.OverField_pb2 as SupplyBoxInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from server.notice_sync import _rel_time as rel_time


@packet_handler(MsgId.SupplyBoxInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SupplyBoxInfoRsp_pb2.SupplyBoxInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.next_reward_time = int(rel_time) + 600

        session.send(MsgId.SupplyBoxInfoRsp, rsp, packet_id)  # 1891,1892
