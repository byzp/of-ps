from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import EmotionMoonInteractReq, EmotionMoonInteractRsp, StatusCode
import utils.db as db


@packet_handler(MsgId.EmotionMoonInteractReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = EmotionMoonInteractReq()
        req.ParseFromString(data)

        # 交互状态持久化(kv ns=emotion_moons)
        raw = db.get_kv(session.player_id, "emotion_moons", "ids", b"")
        ids = {x for x in raw.decode().split(",") if x}
        ids.add(str(req.emotion_moon_id))
        db.set_kv(
            session.player_id,
            "emotion_moons",
            "ids",
            ",".join(sorted(ids, key=lambda x: int(x))).encode(),
        )

        rsp = EmotionMoonInteractRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.info.moon_id = req.emotion_moon_id
        rsp.info.interacted = True

        session.send(MsgId.EmotionMoonInteractRsp, rsp, packet_id)
