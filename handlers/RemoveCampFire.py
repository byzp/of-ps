from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    RemoveCampFireReq,
    RemoveCampFireRsp,
    RemoveCampFireNotice,
    StatusCode,
)
from server.scene_data import get_session
import utils.db as db
from handlers.PlaceCampFire import _key, camp_fire_lock


@packet_handler(MsgId.RemoveCampFireReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RemoveCampFireReq()
        req.ParseFromString(data)

        with camp_fire_lock:
            db.del_kv(
                0,
                Config.CAMPFIRE_NAMESPACE,
                _key(session.scene_id, session.channel_id, req.camp_fire_id),
            )

        rsp = RemoveCampFireRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.RemoveCampFireRsp, rsp, packet_id)  # 1923,1924

        notice = RemoveCampFireNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.camp_fire_id.append(req.camp_fire_id)
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.RemoveCampFireNotice, notice, 0)  # 1926
