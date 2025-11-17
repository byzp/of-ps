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


def get_recorder(
    scene_id: int, channel_id: int, player_id: Optional[int] = None
) -> Optional[Any]:
    with lock_scene:
        ch = _scene.get(scene_id)
        if not ch:
            return None
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
                _chat_msg["default"][scene_id][channel_id].append([True, player_id, text])
            else:
                _chat_msg["default"][scene_id][channel_id].append([False, player_id, expression])


def get_scene_id(player_id: int) -> Optional[int]:
    return 9999
    with lock_scene:
        for scene_id, channels in _scene.items():
            for channel_id, players in channels.items():
                if player_id in players:
                    return scene_id
    return 9999


def get_channel_id(player_id: int) -> Optional[int]:
    return 9853195
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

                p = sd.player
                p.player_id = session.player_id
                p.player_name = session.player_name

                team = p.team
                char = team.char_1
                char.char_id = 101001

                outfit = char.outfit_preset
                outfit.hat = 4012021
                outfit.hair = 4012012
                outfit.clothes = 4200373

                hat_ds = outfit.hat_dye_scheme
                c = hat_ds.colors.add()
                c.pos = 1
                c.red = 4
                c.green = 17
                c = hat_ds.colors.add()
                c.red = 172
                c.blue = 29
                hat_ds.is_un_lock = True

                hair_ds = outfit.hair_dye_scheme
                hc = hair_ds.colors.add()
                hc.red = 255
                hc.green = 169
                hc.blue = 134
                hair_ds.is_un_lock = True

                cloth_ds = outfit.cloth_dye_scheme
                cc = cloth_ds.colors.add()
                cc.pos = 5
                cc.red = 255
                cc.green = 92
                cc.blue = 48
                cc = cloth_ds.colors.add()
                cc.pos = 1
                cc.red = 229
                cc.blue = 20
                cloth_ds.is_un_lock = True

                outfit.hide_info.SetInParent()
                outfit.pend_up_face = 4013024
                outfit.pend_up_face_dye_scheme.is_un_lock = True

                app = char.character_appearance
                app.badge = 5000
                app.umbrella_id = 4060
                app.logging_axe_instance_id = 52
                app.water_bottle_instance_id = 76
                app.mining_hammer_instance_id = 72
                app.fishing_rod_instance_id = 77

                pos = char.pos
                pos.x = 0
                pos.y = 0
                pos.z = 0

                rot = char.rot
                rot.y = 18000

                char.weapon_id = 1102401
                char.weapon_star = 1
                char.char_lv = 14
                char.char_star = 3
                char.char_break_lv = 20

                a = char.armors.add()
                a.armor_id = 2112004
                a = char.armors.add()
                a.armor_id = 2123004
                a = char.armors.add()
                a.armor_id = 2131004

                pstr = char.posters.add()
                pstr.poster_id = 10430
                pstr.poster_star = 1
                pstr = char.posters.add()
                pstr.poster_id = 10870
                pstr.poster_star = 1
                res = notice.SerializeToString()
                if session.player_id == player_id:
                    # 如果是自己，向其他玩家广播
                    up_scene_action(session.scene_id, session.channel_id, res)
                else:
                    players.append(res)
        return players
