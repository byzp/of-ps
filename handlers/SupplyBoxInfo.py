from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import SupplyBoxInfoRsp, StatusCode
from server import activities


@packet_handler(MsgId.SupplyBoxInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SupplyBoxInfoRsp()
        next_reward_time = activities.supply_next_reward_time(session.player_id)
        if next_reward_time is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
        else:
            rsp.next_reward_time = next_reward_time
            rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.SupplyBoxInfoRsp, rsp, packet_id)
