from config import Config
import itertools
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    PlaceMoonSpotReq,
    PlaceMoonSpotRsp,
    PlaceMoonSpotNotice,
    MoonSpotOperateType,
    StatusCode,
)
from server.scene_data import get_session

import utils.db as db
from proto.net_pb2 import MoonSpotData
from utils.refresh import moon_spot_ttl_ms

_id_iter = itertools.count(1)


def _key(scene, channel, instance_id):
    return f"{scene}:{channel}:{instance_id}"


def _load_scene(scene, channel):
    """读取该场景频道的存活信标(惰性剔除过期并删除键)"""
    now_ms = int(time.time() * 1000)
    ttl = moon_spot_ttl_ms()
    out = []
    for k in db.get_kv_keys(0, Config.MOON_SPOT_NAMESPACE):
        if not k.startswith(f"{scene}:{channel}:"):
            continue
        raw = db.get_kv(0, Config.MOON_SPOT_NAMESPACE, k)
        if not raw:
            continue
        m = MoonSpotData()
        m.ParseFromString(raw)
        if m.create_time + ttl < now_ms:
            # 过期信标: 请求时惰性删除(延迟刷新)
            db.del_kv(0, Config.MOON_SPOT_NAMESPACE, k)
            continue
        out.append(m)
    out.sort(key=lambda m: m.create_time)
    return out


@packet_handler(MsgId.PlaceMoonSpotReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlaceMoonSpotReq()
        req.ParseFromString(data)

        rsp = PlaceMoonSpotRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.PlaceMoonSpotRsp, rsp, packet_id)  # 2743,2744

        notice = PlaceMoonSpotNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.operate = req.operate
        notice.data.CopyFrom(req.data)
        notice.player_id = session.player_id

        scene, channel = session.scene_id, session.channel_id
        if req.operate == MoonSpotOperateType.OperateType_Place:
            if not notice.data.instance_id:
                notice.data.instance_id = next(_id_iter)
            if not notice.data.create_time:
                notice.data.create_time = int(time.time() * 1000)
            # 放置: 写库(每对象一键, 过期由请求时惰性剔除)
            spots = _load_scene(scene, channel)
            while len(spots) >= 50:  # 单频道上限, 淘汰最旧
                oldest = spots.pop(0)
                db.del_kv(
                    0,
                    Config.MOON_SPOT_NAMESPACE,
                    _key(scene, channel, oldest.instance_id),
                )
            db.set_kv(
                0,
                Config.MOON_SPOT_NAMESPACE,
                _key(scene, channel, notice.data.instance_id),
                notice.data.SerializeToString(),
            )
        elif req.operate == MoonSpotOperateType.OperateType_Remove:
            db.del_kv(
                0,
                Config.MOON_SPOT_NAMESPACE,
                _key(scene, channel, req.data.instance_id),
            )

        for s in get_session():
            if s.scene_id == scene and s.channel_id == channel:
                s.send(MsgId.PlaceMoonSpotNotice, notice, 0)  # 2746
