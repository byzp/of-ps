from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import SceneSitVehicleReq, SceneSitVehicleRsp, StatusCode
from utils.trace import trace


@packet_handler(MsgId.SceneSitVehicleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneSitVehicleReq()
        req.ParseFromString(data)

        # 参考 SceneSitChair
        rsp = SceneSitVehicleRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.player_id = session.player_id
        rsp.chair_id = req.chair_id
        rsp.seat_id = req.seat_id
        rsp.is_sit = req.is_sit
        trace("sit_vehicle", player=session.player_id, chair=req.chair_id,
              seat=req.seat_id, sit=req.is_sit)
        session.send(MsgId.SceneSitVehicleRsp, rsp, packet_id)  # 2765,2766
