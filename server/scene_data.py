import threading
from collections import defaultdict
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
            return
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
    return 9999
    with lock_scene:
        for scene_id, channels in _scene.items():
            for channel_id, players in channels.items():
                if player_id in players:
                    return scene_id
    return 9999


def get_channel_id(player_id: int) -> Optional[int]:
    return 1
    with lock_scene:
        for scene_id, channels in _scene.items():
            for channel_id, players in channels.items():
                if player_id in players:
                    return channel_id
    return 9999


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
