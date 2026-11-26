import pickle
import threading
import time
from collections import defaultdict
from google.protobuf.message import DecodeError
from typing import Any, Dict, Optional, List

_scene: Dict[int, Dict[int, Dict[int, Any]]] = defaultdict(lambda: defaultdict(dict))
_action: List = []
_scene_action: Dict[int, Dict[int, List]] = defaultdict(lambda: defaultdict(list))
_chat_msg: List = []
_session_list: List = []
_rec_list: List = []

lock_scene = threading.Lock()
lock_action = threading.Lock()
lock_scene_action = threading.Lock()
lock_chat_msg = threading.Lock()
lock_session = threading.Lock()
lock_rec_list = threading.Lock()

_LOCATION_NS = "player_location"
_LOCATION_KEY = "last"
_LOCATION_SAVE_INTERVAL = 2.0
_last_location_save = {}


def save_session_location(session, force=False):
    now = time.monotonic()
    previous = _last_location_save.get(session.player_id, 0.0)
    if not force and now - previous < _LOCATION_SAVE_INTERVAL:
        return
    position = session.pos.get(session.scene_id)
    rotation = session.scene_player.team.char1.rot
    payload = {
        "scene_id": int(session.scene_id),
        "channel_id": int(session.channel_id),
        "position": position.SerializeToString() if position is not None else b"",
        "rotation": rotation.SerializeToString() if rotation is not None else b"",
    }
    import utils.db as db
    db.set_kv(session.player_id, _LOCATION_NS, _LOCATION_KEY, pickle.dumps(payload))
    _last_location_save[session.player_id] = now


def load_session_location(player_id):
    import utils.db as db
    raw = db.get_kv(player_id, _LOCATION_NS, _LOCATION_KEY)
    if not raw:
        return None
    try:
        payload = pickle.loads(raw)
        if not isinstance(payload, dict):
            return None
        scene_id = int(payload["scene_id"])
        channel_id = int(payload["channel_id"])
        if scene_id <= 0 or channel_id <= 0:
            return None
        return payload
    except (KeyError, TypeError, ValueError, pickle.UnpicklingError):
        return None


def restore_session_location(session):
    payload = load_session_location(session.player_id)
    if not payload:
        return False
    from proto.net_pb2 import Vector3
    session.scene_id = int(payload["scene_id"])
    session.channel_id = int(payload["channel_id"])
    position = Vector3()
    rotation = Vector3()
    try:
        position.ParseFromString(payload.get("position", b""))
        rotation.ParseFromString(payload.get("rotation", b""))
    except DecodeError:
        return False
    if position.SerializeToString():
        session.pos[session.scene_id] = position
        session.scene_player.team.char1.pos.CopyFrom(position)
    if rotation.SerializeToString():
        session.scene_player.team.char1.rot.CopyFrom(rotation)
    return True


def get_session():
    session_tmp = []
    with lock_session:
        for session in _session_list:
            if session.logged_in and session.running:
                session_tmp.append(session)
        return session_tmp


def get_recorder(scene_id: int, channel_id: int) -> Optional[Any]:
    with lock_scene:
        sc = _scene.get(scene_id)
        if not sc:
            return {}
        ch = sc.get(channel_id)
        if not ch:
            return {}
        return dict(ch)


def up_recorder(scene_id: int, channel_id: int, player_id: int, rec_data: Any) -> None:
    with lock_scene:
        with lock_rec_list:
            _scene[scene_id][channel_id][player_id] = rec_data
            rec = (scene_id, channel_id)
            if rec not in _rec_list:
                _rec_list.append(rec)


def up_action(scene_id: int, channel_id: int, msg) -> None:
    with lock_action:
        _action.append([scene_id, channel_id, msg])


def up_scene_action(scene_id: int, channel_id: int, action: Any) -> None:
    with lock_scene_action:
        _scene_action[scene_id][channel_id].append(action)


def up_chat_msg(chat_channel_id: int, scene_id: int, channel_id: int, notice) -> None:
    with lock_chat_msg:
        _chat_msg.append([chat_channel_id, scene_id, channel_id, notice])


def get_scene_id(player_id: int) -> Optional[int]:
    saved = load_session_location(player_id)
    if saved:
        return int(saved["scene_id"])
    with lock_scene:
        for scene_id, channels in _scene.items():
            for channel_id, players in channels.items():
                if player_id in players:
                    return scene_id
    return 9999


def get_channel_id(player_id: int) -> Optional[int]:
    saved = load_session_location(player_id)
    if saved:
        return int(saved["channel_id"])
    with lock_scene:
        for scene_id, channels in _scene.items():
            for channel_id, players in channels.items():
                if player_id in players:
                    return channel_id
    return 1


def get_scene_player(scene_id, channel_id):
    players = []
    with lock_session:
        for session in _session_list:
            if session.running == False or session.logged_in == False:
                continue
            if session.scene_id == scene_id and session.channel_id == channel_id:
                # 获取所有同场景玩家
                players.append(session.scene_player)
        return players
