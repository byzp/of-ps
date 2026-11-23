"""多人组队(MP)内存态管理 — mp 组共享模块

模块级 dict + threading.RLock 维护 team_id → 队伍状态。
仅本服组队; 跨服组队依赖互联路由, 暂不开放。
handler 内对状态的读写请统一 `with mp_team.lock:` 包裹。
"""

import threading
import itertools
import time

import utils.db as db
from utils.pb_create import make_PlayerBriefInfo
from server.scene_data import get_session
from proto.net_pb2 import (
    MPTeamMemberNotice,
    MPBeaconStatus,
    StatusCode,
)
from network.msg_id import MsgId

# 可重入锁: handler 内嵌套调用本模块函数不会死锁
lock = threading.RLock()

# team_id → 队伍状态 dict
_teams = {}
# player_id → team_id
_player_team = {}
# 队伍 id 自增器
_id_iter = itertools.count(1)


def _persist():
    """队伍状态快照落库(kv player_id=0), 创建/加入/退出等变更后调用"""
    try:
        import pickle

        snap = {
            "teams": _teams,
            "player_team": _player_team,
            "id": next(_id_iter),
        }
        db.set_kv(0, "mp_teams", "snapshot", pickle.dumps(snap))
    except Exception:
        pass


def _restore():
    global _id_iter
    try:
        import pickle

        raw = db.get_kv(0, "mp_teams", "snapshot", b"")
        if raw:
            snap = pickle.loads(raw)
            _teams.update(snap.get("teams", {}))
            _player_team.update(snap.get("player_team", {}))
            for _ in range(max(1, int(snap.get("id", 1)))):
                next(_id_iter)
    except Exception:
        pass


_restore()

MAX_MEMBERS = 4  # 默认队伍上限


# 状态操作(调用方需持有 lock)
def create_team(player_id, team_name, mode_id, sub_mode_id, character_id):
    """创建队伍, 调用方需保证 player_id 不在其他队伍中"""
    with lock:
        team_id = next(_id_iter)
        team = {
            "team_id": team_id,
            "team_name": team_name,
            "leader": player_id,
            "mode_id": mode_id,
            "sub_mode_id": sub_mode_id,
            "game_mode": 0,  # EMultiplayerPlayMode 默认模式
            "gameplay_id": 0,
            "max_members": MAX_MEMBERS,
            # player_id → {player_id, character_id, is_ready}
            "members": {},
            # 信标: None 或 {status, position(Vector3), rotation(Vector3),
            # scene_id, channel_id, owner_id}
            "beacon": None,
            # 游戏房间: None 或 {game_start_time(ms), ready(set), exited(set), fg_bytes(dict)}
            "room": None,
        }
        _add_member(team, player_id, character_id)
        _teams[team_id] = team
        _persist()
        return team


def _add_member(team, player_id, character_id):
    team["members"][player_id] = {
        "player_id": player_id,
        "character_id": character_id,
        "is_ready": False,
    }
    _player_team[player_id] = team["team_id"]
    _persist()


def get_team(team_id):
    with lock:
        return _teams.get(team_id)


def get_team_by_player(player_id):
    with lock:
        team_id = _player_team.get(player_id)
        if team_id is None:
            return None
        return _teams.get(team_id)


def join_team(team_id, player_id, character_id):
    """加入队伍, 返回 (team, status)"""
    with lock:
        if _player_team.get(player_id) is not None:
            return None, StatusCode.StatusCode_MP_ALREADY_IN_TEAM
        team = _teams.get(team_id)
        if team is None:
            return None, StatusCode.StatusCode_MP_TEAM_NOT_EXIST
        if len(team["members"]) >= team["max_members"]:
            return None, StatusCode.StatusCode_MP_TEAM_FULL
        if team["room"] is not None:
            return None, StatusCode.StatusCode_MP_TEAM_GAME_STARTED
        _add_member(team, player_id, character_id)
        return team, StatusCode.StatusCode_OK


def remove_member(player_id):
    """把玩家移出所在队伍。
    返回 (team_or_None, team_id): 队伍解散(空了)时 team 为 None。
    队长退出时自动转移队长给最早入队的成员。
    """
    with lock:
        team_id = _player_team.pop(player_id, None)
        if team_id is None:
            return None, 0
        team = _teams.get(team_id)
        if team is None:
            return None, team_id
        team["members"].pop(player_id, None)
        if team["room"] is not None:
            team["room"]["ready"].discard(player_id)
            team["room"]["exited"].discard(player_id)
        if not team["members"]:
            # 队伍空了, 直接销毁
            _teams.pop(team_id, None)
            _persist()
            return None, team_id
        if team["leader"] == player_id:
            # 队长转移(dict 保持插入序, 取最早入队成员)
            team["leader"] = next(iter(team["members"]))
        return team, team_id


def dismiss_team(team_id):
    """解散队伍, 返回原成员 player_id 列表"""
    with lock:
        team = _teams.pop(team_id, None)
        if team is None:
            return []
        member_ids = list(team["members"].keys())
        for pid in member_ids:
            if _player_team.get(pid) == team_id:
                _player_team.pop(pid, None)
        _persist()
        return member_ids


def can_start(team):
    """信标能否开始: 队长默认视为已准备, 其余成员全部准备"""
    for pid, m in team["members"].items():
        if pid == team["leader"]:
            continue
        if not m["is_ready"]:
            return False
    return True


# protobuf 填充辅助(只读 team 状态, 调用方需持有 lock)
def fill_mode_info(team, mode_pb):
    mode_pb.mode_id = team["mode_id"]
    mode_pb.sub_mode_id = team["sub_mode_id"]
    mode_pb.game_mode = team["game_mode"]
    mode_pb.gameplay_id = team["gameplay_id"]


def fill_team_base(team, base_pb):
    fill_mode_info(team, base_pb.mode_info)
    base_pb.team_id = team["team_id"]
    base_pb.team_name = team["team_name"]
    base_pb.current_members = len(team["members"])
    base_pb.max_members = team["max_members"]


def fill_team_members(team, members_pb):
    members_pb.leader = team["leader"]
    for pid, m in team["members"].items():
        p = members_pb.members[pid]
        p.player_id = pid
        try:
            make_PlayerBriefInfo(pid, p.player_brief)
        except Exception:
            pass  # 玩家数据缺失时容错
        char_id = m["character_id"]
        try:
            if not char_id:
                char_id = db.get_players_info(pid, "character_id")[0]
            blobs = db.get_characters(pid, char_id) if char_id else []
            if blobs:
                p.player_info.character.ParseFromString(blobs[0])
        except Exception:
            pass


def fill_team_detail(team, detail_pb):
    fill_team_base(team, detail_pb.base)
    fill_team_members(team, detail_pb.members)


def fill_beacon(team, beacon_pb):
    """把队伍信标状态填进 MPBeacon(无信标时填 UNPLACED)"""
    beacon = team["beacon"]
    beacon_pb.owner_id = team["leader"]
    beacon_pb.name = team["team_name"]
    fill_mode_info(team, beacon_pb.mode_info)
    for pid, m in team["members"].items():
        beacon_pb.members[pid] = m["is_ready"] or pid == team["leader"]
    beacon_pb.can_start = can_start(team)
    if beacon is None:
        beacon_pb.status = MPBeaconStatus.MPBeaconStatus_UNPLACED
        return
    beacon_pb.status = beacon["status"]
    beacon_pb.position.CopyFrom(beacon["position"])
    beacon_pb.rotation.CopyFrom(beacon["rotation"])
    beacon_pb.scene_id = beacon["scene_id"]
    beacon_pb.channel_label = beacon["channel_id"]


# 通知推送
def send_to_players(player_ids, msg_id, notice):
    """向指定玩家集合推送 Notice(packet_id=0), 仅本服在线玩家"""
    targets = set(player_ids)
    for s in get_session():
        if s.player_id in targets:
            s.send(msg_id, notice, 0)


def broadcast(team, msg_id, notice, exclude=None):
    """向队内所有(本服在线)成员推送 Notice"""
    member_ids = set(team["members"].keys())
    if exclude is not None:
        member_ids.discard(exclude)
    send_to_players(member_ids, msg_id, notice)


def notify_members(team, exclude=None):
    """成员变化推 MPTeamMemberNotice"""
    notice = MPTeamMemberNotice()
    notice.status = StatusCode.StatusCode_OK
    notice.team_id = team["team_id"]
    fill_team_members(team, notice.members)
    broadcast(team, MsgId.MPTeamMemberNotice, notice, exclude)  # 2458
