from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import CollectVoiceRegionReq, CollectVoiceRegionRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.CollectVoiceRegionReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectVoiceRegionReq()
        req.ParseFromString(data)

        # 收集到的语音区域持久化于 kv(ns=voice_regions), 重启不丢
        raw = db.get_kv(session.player_id, "voice_regions", "ids", b"")
        ids = {x for x in raw.decode().split(",") if x}
        ids.add(str(req.voice_id))
        db.set_kv(
            session.player_id,
            "voice_regions",
            "ids",
            ",".join(sorted(ids, key=lambda x: int(x))).encode(),
        )

        rsp = CollectVoiceRegionRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.voice_id = req.voice_id
        session.send(MsgId.CollectVoiceRegionRsp, rsp, packet_id)  # 1951,1952
