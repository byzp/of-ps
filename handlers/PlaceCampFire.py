from config import Config
import itertools
import threading
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    PlaceCampFireReq,
    PlaceCampFireRsp,
    PlaceCampFireNotice,
    StatusCode,
)
from server.scene_data import get_session

import utils.db as db
from proto.net_pb2 import CampFire

camp_fire_lock = threading.Lock()
_id_iter = itertools.count(1)


def _key(scene, channel, fid):
    return f"{scene}:{channel}:{fid}"


def _load_scene(scene, channel):
    now_ms = int(time.time() * 1000)
    out = {}
    for k in db.get_kv_keys(0, Config.CAMPFIRE_NAMESPACE):
        if not k.startswith(f"{scene}:{channel}:"):
            continue
        raw = db.get_kv(0, Config.CAMPFIRE_NAMESPACE, k)
        if not raw:
            continue
        cf = CampFire()
        cf.ParseFromString(raw)
        if cf.place_time + Config.CAMPFIRE_TTL_MS < now_ms:
            db.del_kv(0, Config.CAMPFIRE_NAMESPACE, k)
            continue
        out[cf.id] = cf
    return out


def _next_id(existing):
    """场景内自增(取现有最大+1), 跨重启不冲突"""
    return max(existing.keys(), default=0) + 1


@packet_handler(MsgId.PlaceCampFireReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlaceCampFireReq()
        req.ParseFromString(data)

        rsp = PlaceCampFireRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.camp_fire.pos.CopyFrom(req.pos)
        rsp.camp_fire.rot.CopyFrom(req.rot)
        rsp.camp_fire.player_id = session.player_id
        rsp.camp_fire.place_time = int(time.time() * 1000)
        rsp.camp_fire.action_id = req.action_id

        with camp_fire_lock:
            fires = _load_scene(session.scene_id, session.channel_id)
            rsp.camp_fire.id = _next_id(fires)
            fires[rsp.camp_fire.id] = rsp.camp_fire
            db.set_kv(
                0,
                Config.CAMPFIRE_NAMESPACE,
                _key(session.scene_id, session.channel_id, rsp.camp_fire.id),
                rsp.camp_fire.SerializeToString(),
            )

        session.send(MsgId.PlaceCampFireRsp, rsp, packet_id)  # 1913,1914

        notice = PlaceCampFireNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.camp_fires.add().CopyFrom(rsp.camp_fire)
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.PlaceCampFireNotice, notice, 0)  # 1916
