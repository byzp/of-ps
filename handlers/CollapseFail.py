from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import CollapseFailNotice, CollapseFailReq, CollapseFailRsp, StatusCode
from server import minigames
from server.scene_data import get_session


@packet_handler(MsgId.CollapseFailReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        CollapseFailReq().ParseFromString(data)
        accepted, _failure_id = minigames.collapse_failure(session)
        if not accepted:
            session.send(MsgId.CollapseFailRsp, CollapseFailRsp(status=StatusCode.StatusCode_BAD_REQ), packet_id)
            return
        notice = CollapseFailNotice(status=StatusCode.StatusCode_OK, player_id=session.player_id)
        for other in get_session():
            if (
                other.player_id != session.player_id
                and other.scene_id == session.scene_id
                and other.channel_id == session.channel_id
            ):
                other.send(MsgId.CollapseFailNotice, notice, 0)
        session.send(MsgId.CollapseFailRsp, CollapseFailRsp(status=StatusCode.StatusCode_OK), packet_id)
