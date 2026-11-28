from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ActivityTurntableDrawReq, ActivityTurntableDrawRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.ActivityTurntableDrawReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityTurntableDrawReq()
        req.ParseFromString(data)
        rsp = ActivityTurntableDrawRsp(activity_id=req.activity_id)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        activities.draw_turntable(
            session.player_id,
            req.activity_id,
            req.draw_times,
            packet_id,
            rsp,
            pack,
        )
        session.send(MsgId.ActivityTurntableDrawRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
