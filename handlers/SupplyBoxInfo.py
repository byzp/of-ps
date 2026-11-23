from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import SupplyBoxInfoRsp, StatusCode

from utils import supply_box


@packet_handler(MsgId.SupplyBoxInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SupplyBoxInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.next_reward_time = supply_box.next_reward_time(session.player_id)

        session.send(MsgId.SupplyBoxInfoRsp, rsp, packet_id)
