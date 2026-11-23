from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    EmotionMoonInfo,
    GetCollectMoonInfoReq,
    GetCollectMoonInfoRsp,
    StatusCode,
)
from utils.res_loader import res

import utils.db as db


@packet_handler(MsgId.GetCollectMoonInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCollectMoonInfoReq()
        req.ParseFromString(data)

        rsp = GetCollectMoonInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scene_id = req.scene_id
        # 收集进度(由 CollectMoon/EmotionMoonInteract 写入 kv)。
        prefix = str(11000 + req.scene_id)
        raw = db.get_kv(session.player_id, "collected_moons", "ids", b"")
        for mid in (x for x in raw.decode().split(",") if x):
            if mid.startswith(prefix):
                rsp.collected_moon_ids.append(int(mid))
        eraw = db.get_kv(session.player_id, "emotion_moons", "ids", b"")
        for mid in (x for x in eraw.decode().split(",") if x):
            info = rsp.emotion_moons.add()
            info.moon_id = int(mid)
            info.interacted = True
        session.send(MsgId.GetCollectMoonInfoRsp, rsp, packet_id)
