import threading
from collections import defaultdict
from typing import Any, Dict, Optional, List
import proto.OverField_pb2 as pb

_scene: Dict[int, Dict[int, Dict[int, Any]]] = defaultdict(lambda: defaultdict(dict))
_action: Dict[int, list] = {}
_scene_action: Dict[int, Dict[int, List]] = defaultdict(lambda: defaultdict(list))
_chat_msg: Dict[str, Dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
_session_list: List = []

lock_scene = threading.Lock()
lock_action = threading.Lock()
lock_scene_action = threading.Lock()
lock_chat_msg = threading.Lock()
lock_session = threading.Lock()


def get_session():
    session_tmp = []
    with lock_session:
        for session in _session_list:
            if session.logged_in and session.running:
                session_tmp.append(session)
        return session_tmp


def get_recorder(
    scene_id: int, channel_id: int, player_id: Optional[int] = None
) -> Optional[Any]:
    with lock_scene:
        ch = _scene.get(scene_id)
        if not ch:
            return {}
        if player_id is None:
            return ch.get(channel_id)
        return ch.get(channel_id, {}).get(player_id)


def up_recorder(scene_id: int, channel_id: int, player_id: int, rec_data: Any) -> None:
    with lock_scene:
        _scene[scene_id][channel_id][player_id] = rec_data


def up_action(
    player_id: int, player_name: str, scene_id: int, channel_id: int, action_id: int
) -> None:
    with lock_action:
        _action[player_id] = [scene_id, channel_id, action_id, player_name]


def up_scene_action(scene_id: int, channel_id: int, action: Any) -> None:
    with lock_scene_action:
        _scene_action[scene_id][channel_id].append(action)


def up_chat_msg(
    type_: int,
    player_id: int,
    text: str,
    expression: int,
    scene_id: int,
    channel_id: int,
) -> None:
    with lock_chat_msg:
        if type_ == 0:
            if expression == 0:
                _chat_msg["default"][scene_id][channel_id].append(
                    [True, player_id, text]
                )
            else:
                _chat_msg["default"][scene_id][channel_id].append(
                    [False, player_id, expression]
                )


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


def get_and_up_players(scene_id, channel_id, player_id):
    players = []
    with lock_session:
        for session in _session_list:
            if session.running == False or session.logged_in == False:
                continue
            if session.scene_id == scene_id and session.channel_id == channel_id:
                # 获取所有同场景玩家
                notice = pb.ServerSceneSyncDataNotice()
                notice.status = pb.StatusCode_OK

                d = notice.data.add()
                d.player_id = session.player_id

                sd = d.server_data.add()
                sd.action_type = pb.SceneActionType_ENTER

                sd.player.CopyFrom(session.scene_player)
                res = notice.SerializeToString()

                if session.player_id == player_id:
                    # 如果是自己，向其他玩家广播
                    up_scene_action(session.scene_id, session.channel_id, res)
                else:
                    players.append(res)
        return players
