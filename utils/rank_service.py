"""好友榜与全服榜的聚合查询。"""

from proto.net_pb2 import DungeonData

from proto.net_pb2 import ChallengeData

from proto.net_pb2 import BossRushInfo


import utils.db as db
from utils.res_loader import res


def friend_ids(player_id):
    """双向好友(status=2)列表"""
    out = []
    for fid, status in db.get_friend_info(player_id, None, "friend_id,friend_status"):
        if status == 2:
            out.append(fid)
    return out


def _abyss_dungeon_ids(season_id):
    """赛季对应的全部深渊副本 id"""
    stage_id = 1000 if season_id == 9000001 else 0
    if not stage_id:
        for s in res["Abyss"]["abyss_season"]["datas"]:
            if s["i_d"] == season_id:
                stage_id = s["season_stage"]
                break
    for st in res["Abyss"]["abyss_stage"]["datas"]:
        if st["i_d"] == stage_id:
            return [gi["dungeon_i_d"] for gi in st["abyss_stage_group_info"]]
    return []


def abyss_season_summary(player_id, season_id):
    """(通关数, 总用时) —— 未通关返回 (0, 0)"""
    total_time = 0
    finished = 0
    dungeons = db.get_dungeon(player_id)
    for d_id in _abyss_dungeon_ids(season_id):
        blob = dungeons.get(d_id)
        if not blob:
            continue

        tmp = DungeonData()
        tmp.ParseFromString(blob)
        if tmp.last_finish_time > 0:
            finished += 1
            total_time += tmp.last_finish_time
    return finished, total_time


def fill_abyss_season_info(player_id, season_id, season_info):
    """填充单个玩家的 AbyssSeasonInfo(与 AbyssFriendRank 原 _fill_season_info 同口径)"""

    season_info.season_id = season_id
    for st in res["Abyss"]["abyss_stage"]["datas"]:
        if st["i_d"] == (
            1000
            if season_id == 9000001
            else next(
                (
                    s["season_stage"]
                    for s in res["Abyss"]["abyss_season"]["datas"]
                    if s["i_d"] == season_id
                ),
                0,
            )
        ):
            dungeons = db.get_dungeon(player_id)
            for gi in st["abyss_stage_group_info"]:
                d_id = gi["dungeon_i_d"]
                if dungeons.get(d_id):
                    tmp = DungeonData()
                    tmp.ParseFromString(dungeons[d_id])
                    di = season_info.dungeon_info[d_id]
                    di.dungeon_id = d_id
                    di.finish_time = tmp.last_finish_time
            break


def challenge_best_times(player_id, scene_id):
    """{challenge_id: use_time} 该场景已计时的挑战最优记录"""

    out = {}
    for blob in db.get_challenge(player_id, scene_id):
        c = ChallengeData()
        c.ParseFromString(blob)
        if c.use_time > 0:
            prev = out.get(c.challenge_id)
            if prev is None or c.use_time < prev:
                out[c.challenge_id] = c.use_time
    return out


def boss_rush_best_score(player_id, season_id):

    blob = db.get_boss_rush_info(player_id, season_id)
    if not blob:
        return 0
    br = BossRushInfo()
    br.ParseFromString(blob)
    return int(br.best_total_score)


def sort_by_time_asc(entries):
    """[(key, time)] 用时升序, 0/无成绩垫底; 返回排序后的 key 序列"""
    return [k for k, t in sorted(entries, key=lambda kv: (kv[1] <= 0, kv[1], kv[0]))]
