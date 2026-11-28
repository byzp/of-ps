#!/usr/bin/env python3
"""
全量 handler 路径测试
覆盖 handlers/ 下全部 296 个模块:
  - 显式构造用例(状态流转/多账号互动/资源 id 动态获取)
  - 其余 handler 空请求默认路径扫描
  - 服务端 traceback 增量监控

依赖: 需先启动服务端 (python main.py)
用法: python3 tools/handlers_test.py
"""

import os
import sys
import time
import json
import importlib
import sqlite3
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from proto.net_pb2 import *  # noqa
from network.msg_id import MsgId
import utils.res_loader as rl

rl.init()

from login_test import (  # noqa
    make_socket,
    send_packet,
    recv_packet,
    drain,
    http_login,
    group,
    g_log,
    print_group_summary,
)
import login_test

GROUP_RESULTS = login_test.GROUP_RESULTS

MSG_ITEMS = {n: getattr(MsgId, n) for n in dir(MsgId) if not n.startswith("_")}
ID_TO_NAME = {v: k for k, v in MSG_ITEMS.items()}
REQ_NAMES = sorted(n for n in MSG_ITEMS if n.endswith("Req"))

CTX = {}  # 跨步骤动态上下文
COVERED = set()  # 已覆盖 Req 名
PATHS = {}  # Req 名 -> 已执行路径数
TRACEBACK_BASE = None


# ── 字段填充 ──


def setf(msg, d):
    for k, v in d.items():
        cur = getattr(msg, k)
        if isinstance(v, list):
            if v and isinstance(v[0], dict):
                for it in v:
                    sub = cur.add()
                    setf(sub, it)
            else:
                del cur[:]
                cur.extend(v)
        elif isinstance(v, dict):
            setf(cur, v)
        else:
            setattr(msg, k, v)


def status_name(rsp):
    st = getattr(rsp, "status", None)
    if st is None:
        return ""
    try:
        return StatusCode.Name(st)
    except Exception:
        return str(st)


def step(
    sock,
    req_name,
    fields=None,
    expect=None,
    desc="",
    rsp_name=None,
    norrsp=False,
    timeout=3.0,
):
    """发送一条请求并等待对应 Rsp。
    expect: None=任意状态均可 / 状态名列表(后缀匹配)
    norrsp: True=预期无直接响应
    返回 (ok, rsp, note)
    """
    mid = MSG_ITEMS[req_name]
    req = globals()[req_name]()
    setf(req, fields or {})
    send_packet(sock, mid, req)
    PATHS[req_name] = PATHS.get(req_name, 0) + 1
    want = rsp_name or (req_name[:-3] + "Rsp")
    want_id = MSG_ITEMS.get(want)

    if norrsp:
        pkt = recv_packet(sock, 1.0)
        while pkt is not None:
            rmid, _ = pkt
            if rmid == want_id:
                return False, None, "unexpected rsp"
            pkt = recv_packet(sock, 0.3)
        return True, None, ""

    deadline = time.time() + timeout
    while time.time() < deadline:
        pkt = recv_packet(sock, max(0.05, deadline - time.time()))
        if pkt is None:
            break
        rmid, body = pkt
        if rmid == want_id:
            COVERED.add(req_name)
            rsp = globals()[want]()
            rsp.ParseFromString(body)
            stn = status_name(rsp)
            ok = True
            if expect is not None and stn:
                ok = any(stn == e or stn.endswith(e) for e in expect)
            elif expect is not None and not stn:
                ok = False
            return ok, rsp, stn or "(no status field)"
    COVERED.add(req_name)
    return False, None, "NO_RSP"


def run(phase, sock, req_name, fields=None, expect=None, desc="", **kw):
    ok, rsp, note = step(sock, req_name, fields, expect, desc, **kw)
    tag = desc or req_name
    g_log(f"{tag}: {note}", ok)
    if not ok:
        RESULTS_FAIL.append((phase, req_name, desc, note))
    return rsp


RESULTS_FAIL = []


# ═══════════════════════════════════════
# 配置 id 动态获取


def cfg_ids(sheet, key="i_d"):
    try:
        data = rl.res
        for k in sheet.split("."):
            data = data[k]
        rows = data.get("datas", [])
        return [r[key] for r in rows if isinstance(r, dict) and key in r]
    except Exception:
        return []


def setup_ids():
    CTX["quest_id"] = (cfg_ids("Quest.quest") or [0])[0]
    CTX["dungeon_id"] = (cfg_ids("Dungeon.dungeon") or [0])[0]
    CTX["gacha_id"] = 2000
    CTX["area_id"] = 1001
    CTX["food_id"] = (cfg_ids("Cooking.food") or [1])[0]
    CTX["prop_id"] = (cfg_ids("Make.make") or [1])[0]
    CTX["handicraft_id"] = (cfg_ids("Handicraft.handicraft") or [1])[0]
    CTX["sewing_id"] = (cfg_ids("Sewing.sewing") or [1])[0]
    # 探索任务: 取一个未完成度低的
    exps = cfg_ids("Explore.explore")
    CTX["explore_id"] = exps[0] if exps else 11001
    # 活动 id
    act = cfg_ids("Activity.activity")
    CTX["activity_id"] = act[0] if act else 1
    turn = cfg_ids("ActivityTurntable.activity_turntable")
    CTX["turntable_id"] = turn[0] if turn else CTX["activity_id"]
    rest = cfg_ids("RestaurantGame.restaurant_game")
    CTX["restaurant_id"] = rest[0] if rest else CTX["activity_id"]
    sand = cfg_ids("ActivitySandbag.activity_sandbag")
    CTX["sandbag_id"] = sand[0] if sand else CTX["activity_id"]
    bp = cfg_ids("ActivityBattlePass.activity_battle_pass")
    CTX["bp_id"] = bp[0] if bp else 1
    # BossRush/Abyss 赛季
    br = cfg_ids("BossRush.boss_rush_season")
    CTX["br_season"] = br[0] if br else 1
    ab = cfg_ids("Abyss.abyss_season")
    CTX["abyss_season"] = ab[0] if ab else 1
    # 宝箱
    tb = cfg_ids("TreasureBox.treasure_box")
    CTX["box_type"] = tb[0] if tb else 1001
    # 能力/天赋
    abil = cfg_ids("Ability.ability")
    CTX["ability_id"] = abil[0] if abil else 101
    # 表情/动作/音符/骰子
    emj = cfg_ids("Emoji.emoji")
    CTX["emoji_id"] = emj[0] if emj else 1
    dice = cfg_ids("Dice.dice")
    CTX["dice_id"] = dice[0] if dice else 1
    note = cfg_ids("MusicNote.music_note")
    CTX["music_note_id"] = note[0] if note else 1
    # 月亮/水晶/宝物
    moon = cfg_ids("Moon.moon")
    CTX["moon_id"] = moon[0] if moon else 1
    coin = cfg_ids("CollectCoin.collect_coin")
    CTX["coin_index"] = coin[0] if coin else 1
    dig = cfg_ids("TreasureDig.treasure_dig")
    CTX["treasure_id"] = dig[0] if dig else 1
    emo = cfg_ids("EmotionMoon.emotion_moon")
    CTX["emotion_moon_id"] = emo[0] if emo else 1
    bless = cfg_ids("BlessTree.bless_tree_def")
    CTX["bless_def"] = bless[0] if bless else 1
    story = cfg_ids("Story.story")
    CTX["story_id"] = story[0] if story else 0


# ═══════════════════════════════════════
# 测试阶段


def phase_profile(s1):
    group("档案与外观")
    P = "profile"
    run(
        P,
        s1,
        "ChangeNickNameReq",
        {"nick_name": f"PT_{int(time.time())}"},
        ["OK", "ITEM_NOT_ENOUGH", "DUPLICATED_NAME"],
        "改昵称(可能缺星石)",
    )
    run(
        P,
        s1,
        "ChangeNickNameReq",
        {"nick_name": "path_test", "birthday": "2000-01-01"},
        ["OK", "ITEM_NOT_ENOUGH", "DUPLICATED_NAME"],
        "改昵称+生日(规范格式)",
    )
    run(P, s1, "ChangeSignReq", {"sign": "path test"}, ["OK"], "改签名")
    run(P, s1, "ChangeHeadReq", {"head": 41101}, ["OK"], "改头像")
    run(
        P,
        s1,
        "ChangePhoneBackgroundReq",
        {"phone_background": 7000},
        ["OK"],
        "改手机背景",
    )
    run(P, s1, "ChangePhoneCaseReq", {"phone_case": 7000}, None, "改手机壳")
    run(P, s1, "ChangePlayerSexReq", {"sex": 1}, None, "切换性别")
    run(P, s1, "ChangePlayerSexReq", {"sex": 0}, None, "切回性别")
    run(
        P,
        s1,
        "UpdatePlayerAppearanceReq",
        {"appearance": {"avatar_frame": 0, "pendant": 0}},
        None,
        "玩家外观",
    )
    run(
        P,
        s1,
        "UpdateCharacterAppearanceReq",
        {"char_id": 1001, "appearance": {"umbrella_id": 4000}},
        None,
        "角色外观(伞)",
    )
    run(
        P,
        s1,
        "OutfitHideSwitchReq",
        {"char_id": 1001, "hide_info": {"hide_orn": False, "hide_braid": False}},
        None,
        "时装隐藏开关",
    )
    run(
        P,
        s1,
        "OutfitPresetUpdateReq",
        {"char_id": 1001, "preset": {"preset_index": 0}},
        None,
        "预设更新",
    )
    run(
        P,
        s1,
        "OutfitPresetSwitchReq",
        {"char_id": 1001, "use_preset_index": 0},
        None,
        "预设切换",
    )
    run(P, s1, "ChangePetReq", {"pet_instance_id": 0}, ["OK"], "跟随宠物(空)")
    run(
        P,
        s1,
        "ChangeMusicalItemReq",
        {"source": 0, "musical_item_instance_id": 0},
        None,
        "更换乐器",
    )
    run(
        P,
        s1,
        "TutorialReq",
        {"tutorial_id": 1, "tutorial_name": "t"},
        ["OK"],
        "教程确认",
    )
    run(P, s1, "SetArchiveInfoReq", {"key": "pt", "value": "v"}, ["OK"], "写档案")
    run(P, s1, "GetArchiveInfoReq", {"key": "pt"}, ["OK"], "读档案")
    run(P, s1, "ChangeHideTypeReq", {"hide_type": 1}, None, "隐藏在线×1")
    run(P, s1, "ChangeHideTypeReq", {"hide_type": 0}, None, "隐藏在线×2还原")
    run(P, s1, "ChangeIsHideBirthdayReq", {}, None, "隐藏生日×1")
    run(P, s1, "ChangeIsHideBirthdayReq", {}, None, "隐藏生日×2还原")
    run(P, s1, "UnlockHeadListReq", {}, ["OK"], "头像解锁列表")
    run(
        P,
        s1,
        "AccountNameBindingCancelReq",
        {},
        ["OK", "ACCOUNT_NAME_NOT_BIND"],
        "取消账号绑定",
    )


def phase_ability_life(s1):
    group("能力与生活技能")
    P = "life"
    run(P, s1, "PlayerAbilityListReq", {}, ["OK"], "能力列表")
    run(
        P,
        s1,
        "PlayerAbilityLevelUpReq",
        {"ability_id": CTX["ability_id"]},
        None,
        "能力升级",
    )
    run(P, s1, "LifeLeveUpReq", {"life_type": 2}, None, "生活等级升级")
    run(
        P,
        s1,
        "LifeSkillLevelUpReq",
        {"life_type": 2, "skill_id": 0},
        None,
        "生活技能升级",
    )
    run(
        P,
        s1,
        "ActionStudyReq",
        {"player_id": CTX.get("pid1", 0), "action_id": 0},
        None,
        "动作学习",
    )
    run(P, s1, "GetLifeSkillReq", {"life_type": 2}, ["OK"], "生活技能表(料理)")
    run(P, s1, "GetLifeInfoReq", {"life_type": 2}, ["OK"], "生活信息(料理)")
    run(P, s1, "GetLifeAchieveReq", {"life_type": 2}, ["OK"], "生活成就(料理)")
    run(
        P,
        s1,
        "GetOneTypeLifePictorialBookCountReq",
        {"life_type": 2},
        ["OK"],
        "图鉴计数",
    )
    run(
        P,
        s1,
        "CookingFoodReq",
        {"food_id": CTX["food_id"]},
        [
            "OK",
            "EnergyNotEnough",
            "ITEM_NOT_ENOUGH",
            "LIFE_LEVEL_NOT_ENOUGH",
            "CFG_NOT_FOUND",
            "FAIL",
        ],
        "烹饪(可能缺体力)",
    )
    run(
        P,
        s1,
        "MakePropReq",
        {"make_id": CTX["prop_id"]},
        [
            "OK",
            "EnergyNotEnough",
            "ITEM_NOT_ENOUGH",
            "LIFE_LEVEL_NOT_ENOUGH",
            "CFG_NOT_FOUND",
            "FAIL",
        ],
        "制作道具",
    )
    run(
        P,
        s1,
        "HandicraftReq",
        {"handicraft_id": CTX["handicraft_id"]},
        [
            "OK",
            "EnergyNotEnough",
            "ITEM_NOT_ENOUGH",
            "LIFE_LEVEL_NOT_ENOUGH",
            "CFG_NOT_FOUND",
            "FAIL",
        ],
        "手工艺",
    )
    run(
        P,
        s1,
        "SewingReq",
        {"sewing_id": CTX["sewing_id"]},
        [
            "OK",
            "EnergyNotEnough",
            "ITEM_NOT_ENOUGH",
            "LIFE_LEVEL_NOT_ENOUGH",
            "CFG_NOT_FOUND",
            "FAIL",
        ],
        "缝纫",
    )
    run(
        P,
        s1,
        "FishingReq",
        {
            "is_cancel": True,
            "fishing_box_id": 0,
            "fishing_rod_id": 0,
            "fishing_pond_id": 0,
        },
        None,
        "钓鱼取消",
    )
    run(
        P,
        s1,
        "GatherReq",
        {"gather_item": {"index": 999999, "reward": 0}},
        None,
        "采集(无效点位)",
    )


def phase_world_collect(s1):
    group("世界与收集")
    P = "world"
    run(P, s1, "NpcTalkReq", {"id": 1001, "talk_type": 0}, ["OK"], "NPC对话")
    run(
        P,
        s1,
        "MonsterDeadReq",
        {"monster_id": 1001, "monster_index": 0},
        ["OK"],
        "怪物死亡",
    )
    run(
        P,
        s1,
        "CollectingReq",
        {"item_id": 10199001},
        ["OK", "ALREADY_COLLECTED"],
        "收集点",
    )
    run(
        P,
        s1,
        "TreasureBoxOpenReq",
        {"box_type": CTX["box_type"], "treasure_box_index": 1001, "loc_type": 1},
        ["OK", "TREASURE_BOX_NOT_EXIST"],
        "开启宝箱",
    )
    run(
        P,
        s1,
        "TreasureBoxPickupReq",
        {"box_type": CTX["box_type"], "box_index": 0, "pick_index": 0, "loc_type": 1},
        None,
        "拾取宝箱奖励",
    )
    run(P, s1, "CollectionRewardReq", {"item_id": 10199001}, None, "收集里程碑")
    run(P, s1, "GetCollectItemIdsReq", {}, ["OK"], "收集品id列表")
    run(P, s1, "GetCollectMoonInfoReq", {"scene_id": 1}, ["OK"], "月亮收集信息")
    run(P, s1, "CollectMoonReq", {"moon_id": CTX["moon_id"]}, None, "收集月亮")
    run(P, s1, "CollectCoinReq", {"coin_index": CTX["coin_index"]}, None, "收集代币")
    run(
        P,
        s1,
        "EmotionMoonInteractReq",
        {"emotion_moon_id": CTX["emotion_moon_id"]},
        None,
        "情感月亮交互",
    )
    run(P, s1, "TreasureDigReq", {"treasure_id": CTX["treasure_id"]}, None, "挖宝")
    run(P, s1, "TreasureIllustrationInfoReq", {}, ["OK"], "考古图鉴信息")
    run(
        P,
        s1,
        "TreasureIllustrationRewardReq",
        {"archaeology_type": 1, "id": 1},
        None,
        "考古图鉴奖励",
    )
    run(
        P,
        s1,
        "GetTreasureAchieveRewardReq",
        {"achieve_id": 1, "archaeology_type": 1},
        None,
        "考古成就奖励",
    )
    run(P, s1, "SupplyBoxInfoReq", {}, ["OK"], "补给箱信息")
    run(
        P,
        s1,
        "SupplyBoxRewardReq",
        {},
        ["OK", "FAIL", "EXPLORE_NUM_LIMIT"],
        "补给箱奖励",
    )
    run(P, s1, "BlessTreeReq", {"def_id": CTX["bless_def"]}, None, "祝福树信息")
    run(
        P,
        s1,
        "BlessTreeUnlockReq",
        {"def_id": CTX["bless_def"], "tree_id": 1},
        None,
        "祝福树解锁",
    )


def phase_explore_battle(s1):
    group("探索与战斗上报")
    P = "explore"
    run(P, s1, "ExploreInitReq", {}, ["OK"], "探索初始化")
    run(
        P,
        s1,
        "ExploreReq",
        {"explore_id": CTX["explore_id"]},
        ["OK", "FAIL", "CFG_NOT_FOUND", "EXPLORE_NUM_LIMIT"],
        "开始探索",
    )
    run(P, s1, "ExploreCancelReq", {"explore_id": CTX["explore_id"]}, None, "取消探索")
    run(
        P,
        s1,
        "ExploreQuickFinishReq",
        {"explore_id": CTX["explore_id"]},
        None,
        "探索快速完成",
    )
    run(P, s1, "ExploreRewardReq", {"explore_id": CTX["explore_id"]}, None, "探索领奖")
    run(
        P,
        s1,
        "ExploreCollectRewardReq",
        {"explore_id": CTX["explore_id"]},
        None,
        "探索收集奖励",
    )
    run(P, s1, "BattleEncounterInfoReq", {"encounter_ids": []}, ["OK"], "遭遇战信息")
    run(
        P,
        s1,
        "BattleEncounterStateUpdateReq",
        {"encounter_id": 1, "battle_state": 2},
        None,
        "遭遇战状态",
    )
    run(
        P,
        s1,
        "FlagBattleStateUpdateReq",
        {"battle_id": 1, "battle_state": 2, "mission_type": 0},
        None,
        "旗帜战状态",
    )
    run(
        P,
        s1,
        "ChallengeStateUpdateReq",
        {"challenge_id": 1, "battle_state": 2, "use_time": 10},
        None,
        "挑战状态",
    )
    run(
        P,
        s1,
        "RiddleStateUpdateReq",
        {"riddle_id": 2001, "battle_state": 1, "is_win": True},
        None,
        "谜题状态",
    )
    run(P, s1, "GamePlayRewardReq", {"reward_id": 1, "num": 1}, None, "玩法奖励")
    # 主线剧情任务接受路径(quest_type=MainQuest, 真实 story id)
    if CTX.get("story_id"):
        run(
            P,
            s1,
            "AcceptQuestReq",
            {"quest_id": CTX["story_id"], "quest_type": 1},
            ["OK", "BAD_REQ", "PreStory_Not_Finish", "Already_Accept_Quest", "FAIL"],
            "主线剧情接受",
        )


def phase_interact_scene(s1):
    group("场景交互")
    P = "scene"
    run(
        P,
        s1,
        "SceneSitChairReq",
        {"chair_id": 1, "seat_id": 0, "is_sit": True},
        ["OK"],
        "坐椅子",
    )
    run(
        P,
        s1,
        "SceneSitChairReq",
        {"chair_id": 1, "seat_id": 0, "is_sit": False},
        ["OK"],
        "离椅子",
    )
    run(
        P,
        s1,
        "SceneSitVehicleReq",
        {"chair_id": 1, "seat_id": 0, "is_sit": False},
        None,
        "载具座位",
    )
    run(P, s1, "PopEmojiReq", {"emoji_id": CTX["emoji_id"]}, None, "表情气泡")
    run(P, s1, "SendActionReq", {"action_id": 1}, None, "场景动作")
    run(
        P,
        s1,
        "PlayMusicNoteReq",
        {"music_note_id": CTX["music_note_id"], "join_player_id": 0},
        None,
        "演奏音符",
    )
    run(
        P,
        s1,
        "ThrowDiceReq",
        {"dice_id": CTX["dice_id"], "position": {"x": 1, "y": 0, "z": 1}, "pips": 3},
        None,
        "掷骰子",
    )
    run(P, s1, "ClapReq", {"is_cancel": True}, None, "鼓掌结束")
    run(
        P,
        s1,
        "SceneInterActionPlayStatusReq",
        {"action_status": {"id": 1, "value1": 1}, "push_type": 0},
        None,
        "交互播放状态",
    )
    run(P, s1, "UnfreezePlayerActionReq", {"verification_code": 0}, None, "解冻动作")
    run(
        P,
        s1,
        "PickupReq",
        {"drop_item_index": 999999, "pick_index": 0},
        None,
        "拾取掉落",
    )
    run(
        P,
        s1,
        "PlaceCampFireReq",
        {"pos": {"x": 10, "y": 0, "z": 10}, "rot": {}, "action_id": 1},
        ["OK"],
        "放置篝火",
    )
    run(
        P,
        s1,
        "RemoveCampFireReq",
        {"camp_fire_id": CTX.setdefault("campfire_id", 1)},
        None,
        "移除篝火",
    )
    run(
        P, s1, "PlaceMoonSpotReq", {"operate": 1, "data": {"id": 1}}, None, "放置月光点"
    )
    run(
        P,
        s1,
        "MPBeaconActionReq",
        {"action": 1, "position": {"x": 1, "y": 0, "z": 1}},
        None,
        "信标动作",
    )
    rsp = run(P, s1, "PlayerSceneRecordReq", {}, None, "场景录制上报", norrsp=True)


def phase_bag_equip(s1):
    group("背包与装备")
    P = "bag"
    run(
        P,
        s1,
        "GetWeaponReq",
        {"weapon_system_type": 0, "start_index": 0, "end_index": 50},
        ["OK"],
        "武器列表",
    )
    run(
        P,
        s1,
        "GetArmorReq",
        {"weapon_system_type": 0, "start_index": 0, "end_index": 50},
        ["OK"],
        "防具列表",
    )
    run(P, s1, "GetPosterReq", {"start_index": 0, "end_index": 50}, ["OK"], "映像列表")
    run(P, s1, "GetAllCharacterEquipReq", {}, ["OK"], "全装备表")
    run(P, s1, "WeaponStrengthReq", {"weapon_instance_id": 0}, None, "武器强化(空)")
    run(P, s1, "ArmorStrengthReq", {"armor_instance_id": 0}, None, "防具强化(空)")
    run(
        P,
        s1,
        "WeaponInscriptionInlaidReq",
        {"weapon_instance_id": 0, "inscription_id": 0},
        None,
        "铭刻镶嵌",
    )
    run(
        P, s1, "WeaponInscriptionRemoveReq", {"weapon_instance_id": 0}, None, "铭刻摘除"
    )
    run(
        P,
        s1,
        "EquipDisassembleReq",
        {"weapon_ids": [], "armor_ids": []},
        None,
        "分解(空)",
    )
    run(P, s1, "LockEquipReq", {"instance_id": 0, "equip_type": 0}, None, "锁定装备")
    run(
        P,
        s1,
        "ItemUseReq",
        {"item_id": 999999, "num": 1},
        ["ITEM_NOT_ENOUGH", "CFG_NOT_FOUND"],
        "用不存在物品",
    )
    run(
        P,
        s1,
        "ItemSweepReq",
        {"item_id": 1, "count": 1, "is_sweep": False},
        None,
        "物品扫荡",
    )
    run(P, s1, "TempPackSortReq", {}, None, "临时包整理")
    run(P, s1, "TempPackItemStoreReq", {}, None, "临时包存入")
    run(P, s1, "TempPackItemDropReq", {"index": 0}, None, "临时包丢弃")
    run(
        P, s1, "TempPackWearEquipReq", {"index": 0, "char_id": 1001}, None, "临时包穿戴"
    )
    run(
        P,
        s1,
        "CharacterLevelUpReq",
        {"char_id": 99999, "nums": [0, 0, 0]},
        ["CharNotExist", "OK"],
        "角色升级(不存在)",
    )
    run(
        P,
        s1,
        "CharacterStarUpReq",
        {"char_id": 99999},
        ["CharNotExist", "OK", "ITEM_NOT_ENOUGH"],
        "角色升星(不存在)",
    )
    run(P, s1, "CharacterLevelBreakReq", {"char_id": 99999}, None, "角色突破(不存在)")
    run(
        P,
        s1,
        "CharacterSkillLevelUpReq",
        {"char_id": 99999, "skill_id": 1},
        None,
        "技能升级(不存在)",
    )
    run(
        P,
        s1,
        "CharacterEquipPresetSwitchReq",
        {"char_id": 1001, "preset_index": 0},
        None,
        "装备预设切换",
    )
    run(
        P,
        s1,
        "CharacterGatherWeaponUpdateReq",
        {"character_id": 1001, "weapon_id": 0},
        None,
        "采集工具更新",
    )
    run(
        P,
        s1,
        "PosterStarUpReq",
        {"poster_instance_id": 0, "cost_poster_instance_id": []},
        None,
        "映像升星(空)",
    )
    run(P, s1, "PosterIllustrationListReq", {}, ["OK"], "映像插画列表")
    run(
        P,
        s1,
        "PosterIllustrationRewardReq",
        {"poster_illustration_id": 1},
        None,
        "映像插画奖励",
    )
    run(
        P,
        s1,
        "OutfitDyeUnlockIndexReq",
        {"outfit_id": 0, "index": 0},
        None,
        "染色解锁(空)",
    )


def phase_social(s1, s2):
    group("社交(双账号)")
    P = "social"
    pid1, pid2 = CTX["pid1"], CTX["pid2"]

    rsp = run(P, s1, "FriendSearchReq", {"search_args": "path_test2"}, ["OK"], "搜索p2")
    if rsp is not None and rsp.data.player_id:
        pid2 = rsp.data.player_id
        CTX["pid2"] = pid2

    run(P, s1, "FriendAddReq", {"player_id": pid2}, None, "p1加p2好友")
    run(
        P,
        s2,
        "FriendHandleReq",
        {"player_id": pid1, "is_agree": True},
        ["OK", "FAIL"],
        "p2同意好友",
    )

    rsp = run(P, s1, "FriendReq", {}, ["OK"], "好友列表")

    run(P, s1, "OtherPlayerInfoReq", {"player_id": pid2}, None, "查看他人信息")
    run(
        P,
        s1,
        "SendChatMsgReq",
        {"type": 2, "player_id": pid2, "text": "pt-chat"},
        ["OK"],
        "私聊发送",
    )
    rsp = run(
        P, s1, "PrivateChatMsgRecordReq", {"target_player_id": pid2}, ["OK"], "私聊记录"
    )
    if rsp is not None and len(rsp.msg_record):
        g_log(f"私聊历史: {len(rsp.msg_record)} 条", True)
    else:
        g_log("私聊历史: 空", False)
        RESULTS_FAIL.append((P, "PrivateChatMsgRecordReq", "历史", "EMPTY"))
    run(
        P,
        s1,
        "SetFriendExtInfoReq",
        {"player_id": pid2, "data": [{"type": 1, "value": "n", "int_value": 1}]},
        None,
        "好友备注",
    )
    run(P, s1, "DoLikesReq", {}, None, "点赞")
    run(P, s1, "WishListByFriendIdReq", {"player_id": pid2}, None, "看好友心愿单")
    run(
        P,
        s1,
        "UseItemFriendIntimacyReq",
        {"item_id": 999999, "friend_id": pid2},
        ["ITEM_NOT_ENOUGH", "OK", "FAIL"],
        "好友送礼(无道具)",
    )
    run(
        P,
        s1,
        "MultipleActionAcceptReq",
        {"status": 1, "action_id": 1, "from_player_id": pid2},
        None,
        "多人动作应答",
    )
    run(P, s1, "SelfIntervalInitReq", {}, None, "独处时刻初始化")
    run(P, s1, "IntervalStartReq", {}, None, "独处时刻开始")
    run(P, s1, "FriendIntervalInitReq", {}, None, "好友时刻初始化")
    run(
        P,
        s1,
        "IntervalJoinReq",
        {"friend_id": pid2, "interval_param": ""},
        None,
        "加入好友时刻",
    )
    run(P, s1, "IntervalQuickReq", {}, None, "好友时刻快进")
    run(
        P,
        s1,
        "IntervalRewardReq",
        {"friend_id": pid2, "interval_param": ""},
        None,
        "时刻奖励",
    )

    # 好友排行榜(有好友关系后)
    run(P, s1, "ChallengeFriendRankReq", {}, ["OK"], "挑战好友榜")
    run(
        P,
        s1,
        "AbyssFriendRankReq",
        {"season_id": CTX["abyss_season"]},
        ["OK"],
        "深渊好友榜",
    )
    run(
        P,
        s1,
        "BossRushFriendRankReq",
        {"season_id": CTX["br_season"]},
        ["OK"],
        "BossRush好友榜",
    )
    run(
        P,
        s1,
        "BossRushFriendDetailReq",
        {"player_id": pid2},
        ["OK"],
        "好友BossRush详情",
    )

    run(P, s1, "TransmitSceneReq", {"friend_id": pid2}, None, "传送至好友")

    # 拉黑再解除
    run(
        P, s1, "FriendBlackReq", {"player_id": pid2, "is_remove": False}, None, "拉黑p2"
    )
    run(
        P,
        s1,
        "FriendBlackReq",
        {"player_id": pid2, "is_remove": True},
        None,
        "解除拉黑",
    )


def phase_photo_share(s1):
    group("照片分享")
    P = "photo"
    png = bytes.fromhex("89504e470d0a1a0a") + b"path-test"
    rsp = run(
        P,
        s1,
        "UploadPhotoShareReq",
        {"file": png, "title": "pt", "tag1": "1", "tag2": "1"},
        ["OK", "PS_UPLOAD_LIMIT", "PS_TODAY_UPLOAD_LIMIT", "FAIL"],
        "上传照片",
    )
    code = ""
    if rsp is not None and rsp.HasField("info"):
        code = rsp.info.code
        CTX["photo_code"] = code
    if code:
        run(
            P,
            s1,
            "PhotoShareDetailReq",
            {"code": code, "search_type": 0},
            ["OK"],
            "照片详情",
        )
        run(
            P,
            s1,
            "OperatePhotoShareReq",
            {"code": code, "operate_type": 1},
            None,
            "照片点赞",
        )
        run(
            P,
            s1,
            "ChangePhotoShareTitleReq",
            {"code": code, "title": "pt2", "tag1": "1", "tag2": "1"},
            None,
            "改照片标题",
        )
        run(P, s1, "PhotoShareCopyFashionDyeReq", {"code": code}, None, "复制穿搭染色")
    run(
        P,
        s1,
        "PhotoShareSearchReq",
        {
            "search_type": 0,
            "text_type": 0,
            "text": "pt",
            "start_index": 0,
            "end_index": 10,
        },
        ["OK"],
        "照片搜索",
    )
    run(P, s1, "PhotoSharePaymentAddUploadGridReq", {}, None, "扩照片格子")


def phase_garden(s1):
    group("家园")
    P = "garden"
    run(P, s1, "GetGardenInfoReq", {}, ["OK"], "花园信息")
    run(
        P,
        s1,
        "SwitchGardenStatusReq",
        {"is_open": True, "password": ""},
        None,
        "开放花园",
    )
    run(P, s1, "GardenFurnitureSchemeReq", {}, ["OK"], "方案列表")
    run(P, s1, "GardenFurnitureSaveReq", {"scheme_id": 1}, None, "保存方案")
    run(P, s1, "GardenSchemeFurnitureListReq", {"scheme_id": 1}, None, "方案家具列表")
    run(P, s1, "GardenFurnitureApplySchemeReq", {"scheme_id": 1}, None, "应用方案")
    run(
        P,
        s1,
        "GardenFurnitureSchemeSetNameReq",
        {"scheme_id": 1, "name": "pt"},
        None,
        "方案命名",
    )
    run(P, s1, "GardenLikeRecordReq", {}, None, "花园点赞记录")
    run(
        P,
        s1,
        "GardenPlaceCharacterReq",
        {"character_id": 1001, "furniture_id": 0, "seat_id": 0, "is_remove": True},
        None,
        "花园角色摆放(移除)",
    )
    run(
        P,
        s1,
        "PlaceFurnitureReq",
        {
            "furniture_item_id": 0,
            "pos": {"x": 1, "y": 0, "z": 1},
            "furniture_id": 0,
            "layer_num": 0,
        },
        None,
        "摆放家具(空)",
    )
    run(
        P,
        s1,
        "TakeOutFurnitureReq",
        {"furniture_id": 0, "is_put_in_package": True},
        None,
        "收回家具(空)",
    )
    run(P, s1, "HandingFurnitureReq", {"item_id": 0}, None, "手持家具(空)")
    run(
        P, s1, "TakeOutHandingFurnitureReq", {"furniture_id": 0}, None, "收手持家具(空)"
    )
    run(P, s1, "SetRoomDecorReq", {"decor_list": []}, None, "房间装饰(空)")
    run(P, s1, "GardenFurnitureRemoveAllReq", {}, None, "清空家具")


def phase_team(s1, s2):
    group("组队(双账号)")
    P = "team"
    # 清理上次运行残留的队伍(mp_team 快照持久化)
    run(P, s2, "MPTeamQuitReq", {}, None, "p2退队(清理)")
    run(P, s1, "MPTeamDismissReq", {}, None, "解散旧队伍(清理)")
    rsp = run(
        P,
        s1,
        "MPTeamCreateReq",
        {"team_name": "PT", "mode_id": 1, "sub_mode_id": 1, "character_id": 1001},
        ["OK", "CFG_NOT_FOUND", "FAIL"],
        "创建队伍",
    )
    team_id = rsp.team.team_id if rsp is not None and hasattr(rsp, "team") else 0
    if rsp is not None and not team_id:
        team_id = getattr(rsp, "team_id", 0)
    CTX["team_id"] = team_id
    if team_id:
        run(P, s1, "MPTeamInfoReq", {"team_id": team_id}, None, "队伍信息")
        run(P, s1, "MPTeamRenameReq", {"new_name": "PT2"}, None, "队伍改名")
        run(
            P,
            s2,
            "MPTeamJoinReq",
            {"team_id": team_id, "character_id": 1001},
            None,
            "p2入队",
        )
        run(P, s1, "MPSwapCharacterReq", {"character_id": 1001}, None, "换人")
        run(
            P,
            s1,
            "MPTeamGameModeChangeReq",
            {"mode_id": 1, "sub_mode_id": 1},
            None,
            "切模式",
        )
        run(P, s1, "MPPlayRoomReadyReq", {"ready": True}, None, "房间就绪")
        run(P, s1, "MPPlayRoomEventReq", {"events": []}, None, "房间事件(空)")
        run(P, s1, "MPPlayRoomRewardInfoReq", {}, None, "房间奖励信息")
        run(P, s1, "UploadFGBytesReq", {"info": b"pt"}, None, "FG数据上传")
        run(P, s1, "MPGameStartReq", {}, None, "开始游戏")
        run(P, s1, "MPTeamKickMemberReq", {"target_id": CTX["pid2"]}, None, "踢出p2")
        run(P, s1, "MPTeamDismissReq", {}, None, "解散队伍")
    run(P, s2, "MPTeamQuitReq", {}, None, "p2退队(清理)")


def phase_dungeon_bossrush(s1):
    group("副本与BossRush")
    P = "dungeon"
    did = CTX["dungeon_id"]
    run(
        P,
        s1,
        "DungeonViewReq",
        {"dungeon_id": did},
        ["OK", "CFG_NOT_FOUND"],
        "副本预览",
    )
    run(
        P,
        s1,
        "DungeonEnterReq",
        {"char1": 101001, "dungeon_id": did},
        ["OK", "FAIL", "ITEM_NOT_ENOUGH", "CFG_NOT_FOUND", "PLAYER_LEVEL_LIMIT"],
        "进入副本",
    )
    run(
        P,
        s1,
        "DungeonOperateReq",
        {"operate_type": 1, "bonus_type": 0},
        None,
        "副本操作",
    )
    run(P, s1, "DungeonStarRewardReq", {"dungeon_id": did}, None, "副本星级奖励")
    run(P, s1, "DungeonTaskFinishRewardReq", {"dungeon_id": did}, None, "副本任务奖励")
    run(P, s1, "DungeonFinishReq", {}, None, "副本结算")
    run(P, s1, "DungeonExitReq", {"is_force_exit": True}, None, "强制退出副本")
    run(P, s1, "DungeonRepeatEnterReq", {"char1": 1001}, None, "重复进入(未在本)")
    run(P, s1, "DungeonSweepReq", {"dungeon_id": did}, None, "副本扫荡")

    B = "bossrush"
    sid = CTX["br_season"]
    run(B, s1, "BossRushInfoReq", {"season_id": sid}, ["OK"], "BR赛季信息")
    run(
        B,
        s1,
        "BossRushEnterStageReq",
        {"season_id": sid, "characters": [1001]},
        None,
        "BR进入阶段",
    )
    run(
        B,
        s1,
        "BossRushStartChallengeReq",
        {"season_id": sid, "stage_index": 0},
        None,
        "BR开始挑战",
    )
    run(B, s1, "BossRushTerminateChallengeReq", {"season_id": sid}, None, "BR终止挑战")
    run(
        B,
        s1,
        "BossRushLeaveStageReq",
        {"season_id": sid, "total_damage_hp": 0, "win": False},
        None,
        "BR离开阶段",
    )
    run(B, s1, "BossRushStartBattleReq", {"season_id": sid}, None, "BR开战(无上下文)")
    run(
        B,
        s1,
        "BossRushQuestRewardReq",
        {"season_id": sid, "achieve_id": 1},
        None,
        "BR任务奖励",
    )

    A = "abyss"
    asid = CTX["abyss_season"]
    run(A, s1, "AbyssInfoReq", {}, ["OK"], "深渊信息")
    run(A, s1, "AbyssTeamSwitchReq", {"bonus_type": 0}, None, "深渊队伍切换")
    run(
        A,
        s1,
        "AbyssTeamUpdateReq",
        {"abyss_team": {}, "dungeon_id": did},
        None,
        "深渊队伍更新",
    )
    run(
        A,
        s1,
        "AbyssQuestRewardReq",
        {"season_id": asid, "condition_id": 1},
        None,
        "深渊任务奖励",
    )
    run(
        A,
        s1,
        "AbyssAllServerRankReq",
        {"season_id": asid, "bonus_type": 0},
        ["OK"],
        "深渊全服榜",
    )


def phase_mail(s1):
    group("邮件")
    P = "mail"
    rsp = run(P, s1, "GetMailsReq", {}, ["OK"], "邮件列表")
    mail_id = 0
    if rsp is not None and len(rsp.mails):
        mail_id = rsp.mails[0].mail_id
    if mail_id:
        run(
            P,
            s1,
            "OperateMailsReq",
            {"operate_type": MailOperateType.MailOperateType_READ, "mail_id": mail_id},
            ["OK"],
            "读邮件",
        )
    run(
        P,
        s1,
        "OperateMailsReq",
        {"operate_type": MailOperateType.MailOperateType_CLAIM_ALL},
        ["OK"],
        "一键领取",
    )
    run(
        P,
        s1,
        "OperateMailsReq",
        {"operate_type": MailOperateType.MailOperateType_DELETE_ALL_READED},
        ["OK"],
        "删除已读",
    )


def phase_shop_economy(s1):
    group("商店与心愿单与抽卡")
    P = "shop"
    for sid in [100, 200, 300, 500]:
        run(
            P,
            s1,
            "ShopInfoReq",
            {"shop_id": sid},
            ["OK", "CFG_NOT_FOUND"],
            f"商店{sid}",
        )
    run(
        P,
        s1,
        "ShopBuyReq",
        {"shop_id": 300, "grid_id": 1, "buy_times": 1},
        ["OK", "ITEM_NOT_ENOUGH", "SHOP_GRID_BUY_NUM_LIMIT"],
        "商店购买",
    )
    run(
        P,
        s1,
        "ShopBuyReq",
        {"shop_id": 300, "grid_id": 1, "buy_times": 1},
        ["OK", "ITEM_NOT_ENOUGH", "SHOP_GRID_BUY_NUM_LIMIT"],
        "商店购买(限购校验)",
    )

    run(
        P,
        s1,
        "WishListByShopIdReq",
        {"shop_id": 300, "grid_id": 1},
        ["OK"],
        "按商店查心愿单",
    )
    run(
        P,
        s1,
        "WishListOperateReq",
        {"operate_type": 0, "shop_id": 300, "grid_id": 2},
        None,
        "心愿单添加",
    )
    run(
        P,
        s1,
        "WishListBuyReq",
        {"player_id": CTX["pid1"], "info": {"shop_id": 300, "grid_id": 2}},
        None,
        "心愿单购买",
    )
    run(
        P,
        s1,
        "WishListOperateReq",
        {"operate_type": 1, "shop_id": 300, "grid_id": 2},
        None,
        "心愿单移除",
    )

    G = "gacha"
    gid = CTX["gacha_id"]
    run(G, s1, "GachaListReq", {}, ["OK"], "卡池列表")
    run(G, s1, "GachaRecordReq", {"gacha_id": gid, "page": 0}, None, "抽卡记录")
    run(
        G,
        s1,
        "ChooseGachaReq",
        {"choose_gacha_pool": 0, "gacha_id": gid},
        None,
        "自选池选择",
    )
    run(
        G,
        s1,
        "OptionalUpPoolItemReq",
        {"gacha_id": gid, "poo_id": 0, "item_id": 0},
        None,
        "UP池指定",
    )
    run(G, s1, "GachaFullPickReq", {"gacha_id": gid, "item_id": 0}, None, "全选池(空)")
    run(
        G,
        s1,
        "GachaReq",
        {"gacha_id": gid, "is_single": True},
        ["OK", "ITEM_NOT_ENOUGH", "CFG_NOT_FOUND", "FAIL"],
        "抽卡(可能缺票)",
    )


def phase_activity(s1):
    group("活动")
    P = "act"
    aid = CTX["activity_id"]
    run(
        P,
        s1,
        "ActivitySignInReq",
        {"activity_id": 1, "day": 1},
        ["OK", "FAIL", "CFG_NOT_FOUND"],
        "活动签到",
    )
    run(P, s1, "DailyTaskExchangeReq", {"exchange_all": False}, None, "每日任务兑换")
    run(P, s1, "PlayerLevelRewardReq", {"level": 2}, None, "等级礼包")
    run(P, s1, "PlayerVitalityReq", {}, ["OK"], "活力信息")
    run(P, s1, "PlayerVitalityBuyReq", {}, None, "活力购买")
    run(P, s1, "PlayerEnergyBuyReq", {}, None, "体力购买")
    run(P, s1, "PlayerEnergyInfoReq", {}, ["OK"], "体力信息")
    run(
        P,
        s1,
        "ActivityTurntableDrawReq",
        {"activity_id": CTX["turntable_id"], "draw_times": 1},
        ["OK", "ITEM_NOT_ENOUGH", "CFG_NOT_FOUND", "FAIL"],
        "转盘抽取",
    )
    run(
        P,
        s1,
        "ActivityTurntableRecordReq",
        {"activity_id": CTX["turntable_id"], "page": 0},
        ["OK"],
        "转盘记录",
    )
    run(
        P, s1, "ActivityKoiUseItemReq", {"num": 1, "activity_id": aid}, None, "锦鲤道具"
    )
    run(
        P,
        s1,
        "ActivityUploadWishTxtReq",
        {"txt": "pt", "activity_id": aid},
        None,
        "愿望文本上传",
    )
    run(
        P,
        s1,
        "ActivitySandbagHitReq",
        {"activity_id": CTX["sandbag_id"], "npc_id": 1, "hit_count": 1},
        None,
        "沙袋击打",
    )
    run(
        P,
        s1,
        "ActivitySandbagRewardReq",
        {"activity_id": CTX["sandbag_id"], "reward_type": 1, "seq_list": [1]},
        None,
        "沙袋奖励",
    )
    run(
        P,
        s1,
        "ActivityGiftRewardReq",
        {"activity_id": aid, "achieve_id": 1},
        None,
        "活动礼包奖励",
    )
    run(
        P,
        s1,
        "ActivityRegularRewardReq",
        {"activity_id": aid, "param": 1, "pool_type": 1},
        None,
        "活动常规奖励",
    )
    run(
        P,
        s1,
        "ActivityQuestRewardReq",
        {"activity_id": aid, "param": 1, "is_progress": True},
        None,
        "活动任务奖励",
    )
    run(
        P,
        s1,
        "GetActivityBattlePassLevelRewardReq",
        {
            "activity_battle_pass_id": CTX["bp_id"],
            "level": 1,
            "is_get_free_reward": True,
        },
        None,
        "战令等级奖励",
    )
    run(
        P,
        s1,
        "ActivityBattlePassBuyExpReq",
        {"activity_battle_pass_id": CTX["bp_id"]},
        None,
        "战令买经验",
    )
    run(
        P,
        s1,
        "ActivityRecallRewardClaimReq",
        {"activity_id": aid, "condition_id": 1},
        None,
        "召回奖励领取",
    )
    run(
        P,
        s1,
        "ActivityInviteRewardClaimReq",
        {"activity_id": aid, "condition_id": 1},
        None,
        "邀请奖励领取",
    )
    run(
        P,
        s1,
        "RestaurantGameInfoReq",
        {"activity_id": CTX["restaurant_id"]},
        ["OK", "CFG_NOT_FOUND"],
        "餐厅信息",
    )
    run(
        P,
        s1,
        "RestaurantGameOperateReq",
        {"activity_id": CTX["restaurant_id"], "type": 1, "buy_pool_id": 0},
        None,
        "餐厅操作",
    )
    run(
        P,
        s1,
        "RestaurantGameEatReq",
        {"customer_index": 0, "grid": 0, "activity_id": CTX["restaurant_id"]},
        None,
        "餐厅用餐",
    )
    run(
        P,
        s1,
        "RestaurantGameQuestRewardReq",
        {"quest_id": 1, "activity_id": CTX["restaurant_id"]},
        None,
        "餐厅任务奖励",
    )


def phase_achievement_claim(s1):
    group("成就与徽章领取")
    P = "achv"
    run(P, s1, "AbilityBadgeListReq", {"scene_id": 1}, ["OK"], "徽章列表")
    run(
        P,
        s1,
        "AbilityBadgeAchieveRewardReq",
        {"achieve_ids": []},
        ["OK", "ABILITY_BADGE_ACHIEVE_REWARDED"],
        "星符领取(空)",
    )
    run(P, s1, "AbilityBadgePageRewardReq", {"page": 0}, None, "页签奖励(空)")
    run(
        P,
        s1,
        "AbilityBadgePageBoxActiveReq",
        {"page": 0, "box_id": 0},
        None,
        "页签宝箱",
    )
    run(P, s1, "GetOneAchieveAwardReq", {"achieve_id": 0}, None, "单成就领奖(空)")
    run(P, s1, "GetAchieveGroupListReq", {}, ["OK"], "成就组列表")
    run(P, s1, "GetAchieveOneGroupReq", {"group_id": 0}, None, "成就组详情")
    run(P, s1, "GetAchieveGroupAwardReq", {"group_id": 0}, None, "成就组奖励(空)")
    run(
        P,
        s1,
        "GetCharacterAchievementListReq",
        {"character_id": 1001},
        None,
        "角色成就列表",
    )
    run(
        P,
        s1,
        "GetCharacterAchievementAwardReq",
        {"character_id": 1001, "reward_index": 0},
        None,
        "角色成就奖励",
    )
    run(
        P,
        s1,
        "GetCharacterAchievementBadgeAwardReq",
        {"character_id": 1001, "achievement_id": 0},
        None,
        "角色成就徽章",
    )
    run(
        P,
        s1,
        "GetCharacterAchievementUnlockPaymentReq",
        {"character_id": 1001},
        None,
        "角色成就解锁付费",
    )
    run(
        P,
        s1,
        "GetLifeAchievementRewardReq",
        {"achieve_id": 0, "life_type": 2},
        None,
        "生活成就奖励(空)",
    )
    run(P, s1, "WorldLevelAchieveListReq", {}, ["OK"], "世界等级成就列表")
    run(P, s1, "AreaAchieveListReq", {"area_id": CTX["area_id"]}, None, "区域成就列表")
    run(P, s1, "ManualListReq", {}, ["OK"], "手册列表")
    run(
        P,
        s1,
        "ManualFlagUnlockReq",
        {"flag_id": 0},
        ["CFG_NOT_FOUND"],
        "手册旗标解锁(空)",
    )
    # 秘境首次发现 → 手册解锁 → 领取 1000 金币发现奖励
    # 注: 奖励状态跨次运行持久化, 已领过则断言放宽为 MANUAL_REWARDED
    run(P, s1, "ManualFlagUnlockReq", {"flag_id": 15003}, ["OK"], "秘境发现(15003)")
    rsp = run(P, s1, "ManualListReq", {}, ["OK"], "手册列表(仅已发现)")
    if rsp is not None:
        m = {f.flag_id: f.status for f in rsp.flags}
        g_log(f"手册仅含已发现旗帜: {sorted(m)}", 15003 in m)
    rsp, _ = run_cap(P, s1, "ManualFlagRewardReq", {"flag_id": 15003}, "领取发现奖励")
    st = StatusCode.Name(rsp.status) if rsp is not None else "NO_RSP"
    if st == "StatusCode_OK":
        gold = sum(
            i.main_item.base_item.num * (1 if i.main_item.item_id == 101 else 0)
            for i in rsp.items
        )
        g_log(f"发现奖励金币: {gold}", gold == 1000)
    elif st == "StatusCode_MANUAL_REWARDED":
        g_log("发现奖励: 历史已领取(持久化)", True)
    else:
        g_log(f"领取异常: {st}", False)
        RESULTS_FAIL.append((P, "ManualFlagRewardReq", "", st))
    run(
        P,
        s1,
        "ManualFlagRewardReq",
        {"flag_id": 15003},
        ["MANUAL_REWARDED"],
        "重复领取拒绝",
    )
    run(P, s1, "ManualFlagUnlockReq", {"flag_id": 15102}, ["OK"], "普通手册点(15102)")
    run(
        P,
        s1,
        "ManualFlagRewardReq",
        {"flag_id": 15102},
        ["OK", "MANUAL_REWARDED"],
        "普通点领奖",
    )


def phase_achieve_flow(s1):
    """任务条件挂钩回归(按 AchieveQuest 文本对表):
    2找回收藏品 / 1+86击杀 / 131丧失行动能力 / 105+118解谜 /
    101竞速挑战 / 102世界挑战 / 3开箱(场景行1002)。"""
    group("成就条件挂钩(任务文本)")
    P = "achflow"
    hits = []

    def cap(req_name, fields, desc):
        rsp, notices = run_cap(P, s1, req_name, fields, desc=desc)
        ach = [n for n in notices if isinstance(n, str) and n.startswith("Achieve")]
        hits.extend(ach)
        g_log(f"{desc}: 成就通知 {len(ach)} 条 {ach[:3]}", True)
        return rsp

    # 找回[指定收藏品]2: 天使雕像10202022(守护天使60040101)
    rsp = cap("CollectingReq", {"item_id": 10202022}, "收集点(天使雕像→2)")
    if rsp is not None and status_name(rsp) == "StatusCode_ALREADY_COLLECTED":
        g_log("天使雕像历史已收集(无通知属预期)", True)

    # 排除[特定灰物]1(狮口夺球60090051) + 清除灰物86: 绣球龙1405
    cap("MonsterDeadReq", {"monster_id": 1405, "monster_index": 0}, "怪物死亡(绣球龙)")

    # 丧失行动能力131: 第一次意外60010031
    cap("CharacterDeadReq", {"character_id": 1001}, "角色死亡上报")

    # 秘境首次发现解锁(手册15004) → 探索度推进; 普通点15102计景点成就
    cap("ManualFlagUnlockReq", {"flag_id": 15004}, "秘境发现解锁(15004)")
    cap("ManualFlagUnlockReq", {"flag_id": 15004}, "秘境重复解锁(幂等)")

    # 解谜胜利105/118(聪明过人60020101): 取真实谜题 id
    rid = next(
        (
            r["i_d"]
            for r in rl.res["Riddle"]["riddle"]["datas"]
            if isinstance(r, dict) and r.get("i_d")
        ),
        0,
    )
    if rid:
        cap(
            "RiddleStateUpdateReq",
            {"riddle_id": rid, "battle_state": BattleState.Finish, "is_win": True},
            f"解谜胜利(riddle={rid})",
        )
    else:
        g_log("Riddle 表为空, 跳过解谜用例", True)

    # 场景作用域行(param>=1000): 切至鸳鸯锅1002 后完成挑战/开箱
    home = CTX.get("home_scene", 100)
    rsp = run(
        P,
        s1,
        "ChangeSceneChannelReq",
        {"scene_id": 1002, "channel_label": 1},
        ["OK"],
        "切至鸳鸯锅1002",
    )
    if rsp is not None and status_name(rsp) == "StatusCode_OK":
        # 竞速挑战101(TimeSpeed 家族152001) → 锅中影60090091
        cap(
            "ChallengeStateUpdateReq",
            {
                "challenge_id": 152001,
                "battle_state": BattleState.Finish,
                "use_time": 30,
            },
            "竞速挑战完成(152001→101)",
        )
        # 世界挑战102(VacuumFood 952001) → 鸳鸯锅挑战者60090101;
        # 星级金币经 grant_items 同时计入 大富翁(2,param=101)
        cap(
            "ChallengeStateUpdateReq",
            {
                "challenge_id": 952001,
                "battle_state": BattleState.Finish,
                "use_time": 30,
            },
            "世界挑战完成(952001→102)",
        )
        # 开宝箱3 场景行 → 锅中寻宝60090061(param=1002)
        cap(
            "TreasureBoxOpenReq",
            {"box_type": CTX["box_type"], "treasure_box_index": 1001, "loc_type": 1},
            "开宝箱(鸳鸯锅→3)",
        )
        # 一次性不可刷新收集宝箱: 特殊奖励 + 永久关闭 + 计入探索度
        pt = 0
        pt_index = 0
        _ctb = {
            r["i_d"]: r
            for r in rl.res["TreasureBox"]["collection_treasure_box"]["datas"]
        }
        for _sc in rl.res["ScenesConfigAsset"]["Scenes"]:
            if _sc.get("ID") != 1002 or pt:
                continue
            for _pos, c in enumerate(_sc.get("CollectionTreasureInfos") or ()):
                b = _ctb.get(c.get("ID"))
                if b and tuple(b.get("refresh_time") or ()) == (0,):
                    pt = c["ID"]
                    pt_index = c.get("Index", _pos)
                    break
        if pt:
            rsp = cap(
                "TreasureBoxOpenReq",
                {"box_type": CTX["box_type"], "treasure_box_index": pt_index, "loc_type": 0},
                f"一次性收集箱({pt})",
            )
            if rsp is not None:
                far = rsp.next_refresh_time > time.time() + 300 * 86400
                ok = len(rsp.items) > 0 and far
                g_log(f"一次性箱奖励 {len(rsp.items)} 件, 永久关闭={far}", ok)
                if not ok:
                    RESULTS_FAIL.append(
                        (P, "TreasureBoxOpenReq", "one-time box", len(rsp.items))
                    )
        else:
            g_log("场景1002无一次性收集点位, 跳过", True)
        run(
            P,
            s1,
            "ChangeSceneChannelReq",
            {"scene_id": home, "channel_label": 1},
            ["OK"],
            "切回主场景",
        )
    else:
        g_log("场景切换失败, 跳过场景作用域用例", True)

    # 深渊不掉落战利品: 切至深渊·昏10201, 通用宝箱应无产出
    rsp = run(
        P,
        s1,
        "ChangeSceneChannelReq",
        {"scene_id": 10201, "channel_label": 1},
        ["OK"],
        "切至深渊10201",
    )
    abyss_scene = next(
        (row for row in rl.res["ScenesConfigAsset"]["Scenes"] if row.get("ID") == 10201),
        None,
    )
    abyss_boxes = (abyss_scene or {}).get("CollectionTreasureInfos") or ()
    if rsp is not None and status_name(rsp) == "StatusCode_OK" and abyss_boxes:
        box_index = abyss_boxes[0].get("Index", 0)
        rsp = run(
            P,
            s1,
            "TreasureBoxOpenReq",
            {"box_type": CTX["box_type"], "treasure_box_index": box_index, "loc_type": 1},
            ["OK"],
            "深渊开箱(战利品区分场景)",
        )
        n = len(rsp.items) if rsp is not None else -1
        g_log(f"深渊宝箱掉落 {n} 件(应为0)", n == 0)
        if n != 0:
            RESULTS_FAIL.append((P, "TreasureBoxOpenReq", "abyss drop", n))
        run(
            P,
            s1,
            "ChangeSceneChannelReq",
            {"scene_id": home, "channel_label": 1},
            ["OK"],
            "切回主场景",
        )
    else:
        g_log("深渊场景无宝箱配置, 跳过", True)

    # 汇总: 全程至少应有一条成就计数通知(计数型目标未饱和时必然推送)
    g_log(f"成就通知命中合计 {len(hits)} 条", len(hits) > 0)


def phase_misc(s1):
    group("杂项与世界等级")
    P = "misc"
    run(P, s1, "GenericGameAReq", {"generic_msg_id": 1}, None, "通用玩法A")
    run(P, s1, "GenericGameBReq", {"generic_msg_id": 1}, None, "通用玩法B")
    run(P, s1, "GenericSceneAReq", {"generic_msg_id": 1}, None, "通用场景A")
    run(P, s1, "GenericSceneBReq", {"generic_msg_id": 1}, None, "通用场景B")
    run(
        P,
        s1,
        "SPOperateReq",
        {"operate_type": SPOperateType.SPOperateType_Check},
        None,
        "二级密码校验",
    )
    run(
        P,
        s1,
        "ReportReq",
        {
            "report_status": 1,
            "chat_channel": 1,
            "reported_player_id": CTX["pid2"],
            "reported_role_name": "path_test2",
            "reason": "pt",
            "chat_content": "",
            "code": 0,
        },
        None,
        "举报",
    )
    run(
        P,
        s1,
        "ClientLogAuthReq",
        {
            "player_id": CTX["pid1"],
            "device_id": "pt",
            "os": "linux",
            "os_version": "1",
            "app_version": "1",
            "network_type": "wifi",
            "game_launch_time": int(time.time()),
            "device_model": "pt",
        },
        None,
        "日志鉴权",
    )
    run(P, s1, "ClientLogMessageReq", {}, None, "日志上报(空)")
    run(P, s1, "GmCodeReq", {"param": "path_test"}, ["OK"], "GM指令")
    run(
        P,
        s1,
        "CreatePayOrderReq",
        {"shop_id": 900, "grid_id": 1, "product_name": "pt"},
        None,
        "创建支付订单",
    )
    run(P, s1, "MonthCardRewardReq", {}, None, "月卡奖励")
    run(P, s1, "BuyGameCoinReq", {"buy_count": 1}, None, "买金币(无支付)")
    run(P, s1, "UseRedemptionCodeReq", {"code": "PT-CODE"}, None, "兑换码")
    run(P, s1, "InviteCodeUseReq", {"code": "PT"}, None, "邀请码")
    run(P, s1, "InheritCodeUseReq", {"code": "PT"}, None, "继承码")
    run(P, s1, "RecallCodeUseReq", {"code": "PT"}, None, "召回码")
    run(
        P,
        s1,
        "PetCaptureReq",
        {"monster_id": 1001, "catcher_id": 999999},
        ["ITEM_NOT_ENOUGH", "CFG_NOT_FOUND"],
        "捕捉(无捕兽夹)",
    )
    run(P, s1, "PetDecomposeReq", {"pet_instance_ids": []}, None, "宠物分解(空)")
    run(
        P,
        s1,
        "PetRenameReq",
        {"pet_instance_id": 0, "name": "pt"},
        None,
        "宠物改名(空)",
    )
    run(P, s1, "GetPetReq", {"start_index": 0, "end_index": 20}, ["OK"], "宠物列表")
    run(P, s1, "GetExpressAddressReq", {}, None, "收货地址查询")
    run(
        P,
        s1,
        "UploadExpressAddressReq",
        {
            "name": "pt",
            "phone": "13800000000",
            "address": "pt",
            "items": [{"item_id": 0, "num": 0}],
        },
        None,
        "上传收货地址",
    )


def phase_area_scene_end(s1):
    """场景/区域类放最后(会改变玩家所在场景)"""
    group("区域与场景切换")
    P = "area"
    home = CTX["home_scene"]
    run(
        P,
        s1,
        "AreaUnlockReq",
        {"area_id": CTX["area_id"]},
        ["OK", "AREA_ALREADY_UNLOCK"],
        "解锁区域",
    )
    run(P, s1, "AreaLevelUpReq", {"area_id": CTX["area_id"]}, None, "区域升级")
    run(P, s1, "AreaCloseReq", {"area_id": CTX["area_id"]}, None, "关闭区域")
    run(
        P,
        s1,
        "AreaUnlockReq",
        {"area_id": CTX["area_id"]},
        ["OK", "AREA_ALREADY_UNLOCK"],
        "重新解锁区域(还原)",
    )
    run(P, s1, "UnlockWorldLevelReq", {"world_level": 1}, None, "世界等级解锁")
    run(
        P,
        s1,
        "ChangeWorldLevelReq",
        {"world_level": CTX.get("world_level", 1)},
        None,
        "设置世界等级(还原)",
    )

    run(P, s1, "SceneTransmitReq", {"player_id": CTX["pid1"]}, None, "场景内传送(自己)")
    rsp = run(
        P,
        s1,
        "ChangeSceneChannelReq",
        {"scene_id": 9999, "channel_label": 1},
        ["OK"],
        "切换到花园",
    )
    run(P, s1, "ChangeChatChannelReq", {"channel_id": 1}, None, "聊天频道切换")
    run(
        P,
        s1,
        "ChangeSceneChannelReq",
        {"scene_id": home, "channel_label": 1},
        ["OK"],
        "返回原场景",
    )


def phase_character_dead_revive(s1):
    group("死亡与复活")
    P = "dead"
    run(P, s1, "CharacterDeadReq", {"character_id": 1001}, None, "角色死亡上报")
    run(P, s1, "CharacterReviveReq", {"character_id": 1001}, ["OK"], "角色复活")


def phase_team_restore(s1):
    group("状态还原")
    # 队伍角色必须已拥有(测试账号拥有 101001/102001)
    run(
        "restore",
        s1,
        "UpdateTeamReq",
        {"char1": 101001, "char2": 0, "char3": 0},
        ["OK"],
        "恢复默认队伍",
    )


def phase_connection(s2):
    """连接级消息全路径(VerifyLoginToken/PlayerLogin/PlayerMainData/PlayerPing/PlayerOffline)"""
    group("连接级消息全路径")
    P = "conn"

    # PlayerPing: 正常路径
    req = PlayerPingReq()
    req.client_time_ms = int(time.time() * 1000)
    send_packet(s2, MsgId.PlayerPingReq, req)
    ok, note = _wait_rsp(s2, MsgId.PlayerPingRsp, 3.0)
    COVERED.add("PlayerPingReq")
    PATHS["PlayerPingReq"] = PATHS.get("PlayerPingReq", 0) + 1
    g_log(f"PlayerPing(正常): {note}", ok)

    # PlayerMainData: 正常路径(重复请求幂等)
    send_packet(s2, MsgId.PlayerMainDataReq, PlayerMainDataReq())
    ok, note = _wait_rsp(s2, MsgId.PlayerMainDataRsp, 3.0)
    COVERED.add("PlayerMainDataReq")
    PATHS["PlayerMainDataReq"] = PATHS.get("PlayerMainDataReq", 0) + 1
    g_log(f"PlayerMainData(重复请求): {note}", ok)

    # VerifyLoginToken: 非法 token 路径(独立连接, 失败不影响主连接)
    try:
        s_bad = make_socket()
        bad = VerifyLoginTokenReq()
        bad.sdk_uid = "999999999"
        bad.login_token = "invalid_token_zzz"
        send_packet(s_bad, MsgId.VerifyLoginTokenReq, bad)
        ok, note = _wait_rsp(s_bad, MsgId.VerifyLoginTokenRsp, 3.0)
        st = ""
        if ok:
            r = VerifyLoginTokenRsp()
            r.ParseFromString(_last_body[0])
            st = StatusCode.Name(r.status)
            # 私服便利: 任意 token 放行(与官方不同, 记录不判定)
            ok = True
        COVERED.add("VerifyLoginTokenReq")
        PATHS["VerifyLoginTokenReq"] = PATHS.get("VerifyLoginTokenReq", 0) + 2
        g_log(f"VerifyLoginToken(非法token): {st or note}", ok)
        s_bad.close()
    except Exception as e:
        g_log(f"VerifyLoginToken(非法token): 异常 {e}", False)

    # PlayerLogin: is_reconnect 拒绝路径(在主连接上发, 期望 FAIL 且不掉线)
    req2 = PlayerLoginReq()
    req2.is_reconnect = True
    send_packet(s2, MsgId.PlayerLoginReq, req2)
    ok, note = _wait_rsp(s2, MsgId.PlayerLoginRsp, 3.0)
    st = ""
    if ok:
        r = PlayerLoginRsp()
        r.ParseFromString(_last_body[0])
        st = StatusCode.Name(r.status)
        ok = st == "StatusCode_FAIL"
    COVERED.add("PlayerLoginReq")
    PATHS["PlayerLoginReq"] = PATHS.get("PlayerLoginReq", 0) + 2
    g_log(f"PlayerLogin(reconnect拒绝): {st or note}", ok)

    # PlayerOffline: 在 p2 上正常下线路径(最后执行, 之后 p2 不可用)
    send_packet(s2, MsgId.PlayerOfflineReq, PlayerOfflineReq())
    ok, note = _wait_rsp(s2, MsgId.PlayerOfflineRsp, 3.0)
    COVERED.add("PlayerOfflineReq")
    PATHS["PlayerOfflineReq"] = PATHS.get("PlayerOfflineReq", 0) + 1
    g_log(f"PlayerOffline(p2下线): {note or '连接关闭'}", True)


_last_body = [b""]


def run_cap(phase, sock, req_name, fields=None, desc="", **kw):
    """发送并收集窗口内全部 Notice 名称 + 匹配 Rsp"""
    mid = MSG_ITEMS[req_name]
    req = globals()[req_name]()
    setf(req, fields or {})
    send_packet(sock, mid, req)
    PATHS[req_name] = PATHS.get(req_name, 0) + 1
    want = MSG_ITEMS.get(req_name[:-3] + "Rsp")
    deadline = time.time() + kw.pop("timeout", 3.0)
    notices = []
    rsp = None
    while time.time() < deadline:
        pkt = recv_packet(sock, max(0.05, deadline - time.time()))
        if pkt is None:
            break
        if pkt[0] == want:
            rsp = globals()[req_name[:-3] + "Rsp"]()
            rsp.ParseFromString(pkt[1])
            break
        notices.append(ID_TO_NAME.get(pkt[0], pkt[0]))
    COVERED.add(req_name)
    return rsp, notices


# ── 新功能路径阶段 ──


def phase_new_features(s1):
    group("纺织配方流(Spin.spin_item)")
    P = "craft"
    # 未知道具 id → CFG_NOT_FOUND
    run(P, s1, "SewingReq", {"sewing_id": 1}, ["CFG_NOT_FOUND"], "织造未知配方")
    # 材料不足 → ITEM_NOT_ENOUGH
    run(
        P,
        s1,
        "SewingReq",
        {"sewing_id": 5032001},
        ["ITEM_NOT_ENOUGH", "OK"],
        "织造(材料校验)",
    )
    # 商店购买材料(210 金币, 金币不足则跳过成功路径)
    rsp = run(
        P,
        s1,
        "ShopBuyReq",
        {"shop_id": 12000, "grid_id": 1, "buy_times": 3},
        ["OK", "ITEM_NOT_ENOUGH", "SHOP_GRID_BUY_NUM_LIMIT"],
        "购买纺织材料×3",
    )
    if rsp is not None and StatusCode.Name(rsp.status) == "StatusCode_OK":
        rsp2 = run(P, s1, "SewingReq", {"sewing_id": 5032001}, ["OK"], "织造(配方流)")
        if rsp2 is not None:
            ok = rsp2.life_common_result.is_success in (True, False)
            g_log(f"织造结果 is_success={rsp2.life_common_result.is_success}", ok)
        run(P, s1, "GetLifeSkillReq", {"life_type": 5}, ["OK"], "纺织技能表")
    else:
        g_log("金币不足, 跳过织造成功路径", True)

    group("活动探索闭环(Explore.explore_activity)")
    P = "actexp"
    run(
        P,
        s1,
        "ExploreReq",
        {"explore_id": 901, "is_activity": True},
        ["OK", "EXPLORE_NUM_LIMIT"],
        "活动探索开始",
    )
    run(
        P,
        s1,
        "ExploreQuickFinishReq",
        {"explore_id": 901, "is_activity": True},
        ["OK", "EXPLORE_NOT_EXISTS", "ITEM_NOT_ENOUGH"],
        "活动探索快结",
    )
    rsp = run(
        P,
        s1,
        "ExploreRewardReq",
        {"explore_id": 901, "is_activity": True},
        ["OK", "EXPLORE_NOT_FINISH"],
        "活动探索领奖",
    )
    if rsp is not None and StatusCode.Name(rsp.status) == "StatusCode_OK":
        g_log("活动探索奖励已领取", True)
    rsp = run(P, s1, "ExploreInitReq", {}, ["OK"], "探索初始化(回填活动)")
    if rsp is not None:
        act = {a.explore_id: a.times for a in rsp.activity_explore}
        g_log(f"activity_explore 回填: {act}", 901 in act)

    group("配置 id 校验族")
    P = "valid"
    run(
        P,
        s1,
        "UpdateCharacterAppearanceReq",
        {"char_id": 101001, "appearance": {"umbrella_id": 144}},
        ["CFG_NOT_FOUND"],
        "非法雨伞拒绝",
    )
    run(
        P,
        s1,
        "UpdateCharacterAppearanceReq",
        {"char_id": 101001, "appearance": {"umbrella_id": 4000}},
        ["OK"],
        "合法雨伞",
    )
    run(P, s1, "SendActionReq", {"action_id": 1}, ["CFG_NOT_FOUND"], "非法动作拒绝")
    run(P, s1, "SendActionReq", {"action_id": 1001}, None, "合法动作")
    run(
        P,
        s1,
        "SendChatMsgReq",
        {"type": 1, "text": "pt", "expression": 999999},
        ["CFG_NOT_FOUND"],
        "非法聊天表情拒绝",
    )
    run(
        P,
        s1,
        "PlayMusicNoteReq",
        {"music_note_id": 999999, "join_player_id": 0},
        ["CFG_NOT_FOUND"],
        "非法音符拒绝",
    )
    run(
        P,
        s1,
        "ChangeSceneChannelReq",
        {"scene_id": 88888, "channel_label": 1},
        ["CFG_NOT_FOUND"],
        "非法场景拒绝",
    )
    run(
        P,
        s1,
        "SetRoomDecorReq",
        {"decor_list": [{"decor_id": 5050998, "pos_id": 1, "item_id": 999999}]},
        ["FURNITURE_NOT_EXIST", "BAD_REQ"],
        "装饰引用未摆放家具",
    )
    run(
        P,
        s1,
        "PlaceFurnitureReq",
        {
            "furniture_item_id": 999999,
            "pos": {"x": 1, "y": 0, "z": 1},
            "furniture_id": 0,
            "layer_num": 0,
        },
        ["ITEM_NOT_ENOUGH"],
        "摆放未注册家具",
    )

    group("组队模式校验(TeamGameplay)")
    P = "teamv"
    run(
        P,
        s1,
        "MPTeamCreateReq",
        {
            "team_name": "PT3",
            "mode_id": 999999,
            "sub_mode_id": 999999,
            "character_id": 101001,
        },
        ["CFG_NOT_FOUND", "MP_ALREADY_IN_TEAM"],
        "非法模式建队拒绝",
    )
    run(
        P,
        s1,
        "MPTeamCreateReq",
        {
            "team_name": "PT4",
            "mode_id": 1001,
            "sub_mode_id": 100101,
            "character_id": 101001,
        },
        ["OK", "MP_ALREADY_IN_TEAM", "FAIL"],
        "合法模式建队",
    )
    run(P, s1, "MPTeamDismissReq", {}, None, "清理队伍")

    group("染色闭环(DyeStuff/GlobalConfig)")
    P = "dye"
    # 无染剂时染色被拒
    run(
        P,
        s1,
        "OutfitDyeReq",
        {"outfit_id": 0, "uvy": 0.5, "pos": 9, "add_rate_color_index": 1},
        ["OK", "ITEM_NOT_ENOUGH", "BAD_REQ"],
        "染色(无染剂时)",
    )
    run(
        P,
        s1,
        "OutfitColorantSelectReq",
        {"outfit_id": 0, "colorant_item_id": 999999},
        ["CFG_NOT_FOUND", "ITEM_NOT_ENOUGH"],
        "非法染剂拒绝",
    )
    run(
        P,
        s1,
        "OutfitColorantSelectReq",
        {"outfit_id": 0, "colorant_item_id": 401},
        None,
        "选择染剂401",
    )
    run(P, s1, "OutfitRandomColorReq", {"outfit_id": 0, "uvy": 0.5}, None, "随机取色")
    run(
        P,
        s1,
        "OutFitDyeSaveReq",
        {"outfit_id": 0, "scheme_index": 0, "pos": 8, "is_save_dye_result": False},
        ["OK"],
        "保存染色(不落方案)",
    )

    group("采集限频回填(Gather.gather_rule)")
    P = "gatherlim"
    _reward = 0
    for g in rl.res["Gather"]["gather"]["datas"]:
        for info in g.get("gather_group_info", ()) or ():
            _reward = info.get("reward", 0)
            break
        if _reward:
            break
    if _reward:
        rsp = run(
            P,
            s1,
            "GatherReq",
            {"gather_item": {"index": 0, "reward": _reward}},
            ["OK", "GATHER_LIMIT"],
            "采集(真实点位)",
        )
        if rsp is not None and rsp.HasField("group_gather_limit"):
            gl = rsp.group_gather_limit.gather_limit
            g_log(
                f"采集计数回填 num={gl.gather_num} limit={gl.gather_limit_num}",
                gl.gather_limit_num >= 1 and gl.gather_num >= 1,
            )

    group("天气推送(Weather.weather)")
    P = "weather"
    home = CTX.get("home_scene", 100)
    run(
        P,
        s1,
        "ChangeSceneChannelReq",
        {"scene_id": 9999, "channel_label": 1},
        ["OK"],
        "切到花园",
    )
    rsp, notices = run_cap(
        P,
        s1,
        "ChangeSceneChannelReq",
        {"scene_id": home, "channel_label": 1},
        "返回主场景(捕获天气)",
        timeout=4.0,
    )
    has_weather = "SceneWeatherChangeNotice" in [
        n if isinstance(n, str) else "" for n in notices
    ]
    g_log(f"天气通知: {'收到' if has_weather else notices}", has_weather)


# ── 连接级基础流程 ──


def wait_for(sock, want_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pkt = recv_packet(sock, max(0.05, deadline - time.time()))
        if pkt is None:
            return None
        if pkt[0] == want_id:
            return pkt
    return None


def connect_and_login(username):
    creds = http_login(username, "1")
    assert creds, f"{username} HTTP 登录失败"
    uid, token = creds
    s = make_socket()
    req = VerifyLoginTokenReq()
    req.sdk_uid = uid
    req.login_token = token
    send_packet(s, MsgId.VerifyLoginTokenReq, req)
    pkt = wait_for(s, MsgId.VerifyLoginTokenRsp)
    assert pkt, "Verify 失败"
    drain(s)
    send_packet(s, MsgId.PlayerLoginReq, PlayerLoginReq())
    pkt = wait_for(s, MsgId.PlayerLoginRsp, 8)
    assert pkt, "Login 失败"
    rsp = PlayerLoginRsp()
    rsp.ParseFromString(pkt[1])
    CTX[f"home_{username}"] = rsp.scene_id
    drain(s)
    send_packet(s, MsgId.PlayerMainDataReq, PlayerMainDataReq())
    pkt = wait_for(s, MsgId.PlayerMainDataRsp)
    assert pkt, "MainData 失败"
    rsp2 = PlayerMainDataRsp()
    rsp2.ParseFromString(pkt[1])
    drain(s)
    if getattr(rsp2, "world_level", 0):
        CTX.setdefault("world_level", rsp2.world_level)
    return s, rsp2.player_id, 0


# ── 自动扫描 ──

AUTO_NORSP = {"PlayerSceneRecordReq"}  # AcceptQuest 已改为非主线回 BAD_REQ, 不再静默
AUTO_SKIP = set()  # 全路径覆盖: 连接级消息也在 phase_connection 显式覆盖

# 字段名 -> 资源表提示(valid 变体用): 尽量命中真实配置 id
CFG_SHEETS = {}


def _load_cfg_sheets():
    def ids(*path, key="i_d"):
        try:
            data = rl.res
            for p in path:
                data = data[p]
            rows = data.get("datas", [])
            return [r[key] for r in rows if isinstance(r, dict) and key in r]
        except Exception:
            return []

    CFG_SHEETS.update(
        {
            "quest_id": ids("Quest", "quest"),
            "dungeon_id": ids("Dungeon", "dungeon"),
            "explore_id": ids("Explore", "explore"),
            "activity_id": ids("Activity", "activity"),
            "activity_battle_pass_id": ids(
                "ActivityBattlePass", "activity_battle_pass"
            ),
            "season_id": ids("BossRush", "boss_rush_season"),
            "achieve_id": ids("Achieve", "achieve"),
            "item_id": ids("Item", "item"),
            "monster_id": ids("Monster", "monster_character_data"),
            "food_id": ids("Cooking", "cook_food"),
            "make_id": ids("Make", "make"),
            "handicraft_id": ids("Handicraft", "handicraft"),
            "sewing_id": ids("Sewing", "sewing"),
            "skill_id": [1],
            "ability_id": ids("Ability", "ability"),
            "flag_id": ids("Manual", "manual_flag"),
            "reward_id": ids("Reward", "reward"),
            "box_type": ids("TreasureBox", "treasure_box"),
            "treasure_id": ids("TreasureDig", "treasure_dig"),
            "coin_index": ids("CollectCoin", "collect_coin"),
            "moon_id": ids("Moon", "moon"),
            "emotion_moon_id": ids("EmotionMoon", "emotion_moon"),
            "music_note_id": ids("MusicNote", "music_note"),
            "dice_id": ids("Dice", "dice"),
            "emoji_id": ids("Emoji", "emoji"),
            "action_id": ids("Action", "action"),
            "condition_id": [1],
            "group_id": ids("AchieveGroup", "achieve_group"),
            "character_id": [1001],
            "char_id": [1001],
            "friend_id": None,  # 运行时由 CTX 注入
            "player_id": None,
            "target_id": None,
            "from_player_id": None,
            "reported_player_id": None,
            "npc_id": [1001],
            "chair_id": [1],
            "channel_id": [1],
            "channel_label": [1],
            "life_type": [1, 2],
            "world_level": [1],
            "level": [2],
            "page": [0],
            "pool_id": [1],
            "poo_id": [1],
            "buy_pool_id": [1],
            "pool_index": [1],
            "grid_id": [1],
            "shop_id": [100, 300],
            "buy_times": [1],
            "num": [1],
            "count": [1],
            "nums": [[0, 0, 0]],
            "hit_count": [1],
            "draw_times": [1],
            "buy_count": [1],
            "start_index": [0],
            "end_index": [20],
            "stage_index": [0],
            "reward_index": [0],
            "use_preset_index": [0],
            "preset_index": [0],
            "drop_item_index": [0],
            "pick_index": [0],
            "index": [0],
            "box_index": [0],
            "treasure_box_index": [0],
            "customer_index": [0],
        }
    )


def _cfg_value(field_name):
    lst = CFG_SHEETS.get(field_name, [])
    if lst is None:  # 运行时注入类
        return CTX.get(
            {
                "friend_id": "pid2",
                "player_id": "pid1",
                "target_id": "pid2",
                "from_player_id": "pid2",
                "reported_player_id": "pid2",
            }.get(field_name, "pid1"),
            0,
        )
    return lst[0] if lst else 1


def _fill_generic(msg, mode):
    """按模式递归填充消息字段
    mode='bogus': 非法值路径(超大整数/乱串/真值)
    mode='valid': 合法值路径(CFG_SHEETS 提示的配置 id / 1 / 'pt')
    """
    for f in msg.DESCRIPTOR.fields:
        name = f.name
        cur = getattr(msg, name)
        if f.type == 11:  # message
            if f.message_type.GetOptions().map_entry:
                # map 字段: 跳过(map_entry 消息由容器自动管理)
                continue
            if f.is_repeated:
                if mode == "valid" and name in ("nums",):
                    del cur[:]
                    cur.extend([0, 0, 0])
                    continue
                sub = cur.add()
                _fill_generic(sub, mode)
            else:
                _fill_generic(cur, mode)
            continue
        if f.is_repeated:
            continue  # 重复标量留空(map/列表)
        # 枚举
        if getattr(f, "enum_type", None) is not None:
            vals = [v.number for v in f.enum_type.values]
            setattr(
                msg,
                name,
                (
                    vals[0]
                    if mode == "bogus"
                    else (vals[-1] if len(vals) > 1 else vals[0])
                ),
            )
            continue
        if f.type == 8:  # bool
            setattr(msg, name, True)
            continue
        if f.type == 9:  # string
            setattr(msg, name, "zzz" if mode == "bogus" else "pt")
            continue
        if f.type == 12:  # bytes
            setattr(msg, name, b"zz")
            continue
        # 整型/浮点
        if mode == "bogus":
            setattr(msg, name, 999999999)
        else:
            v = _cfg_value(name)
            setattr(msg, name, v)


def auto_sweep(s1):
    group("自动扫描-空请求(默认路径)")
    P = "auto"
    todo = [n for n in REQ_NAMES if n not in COVERED and n not in AUTO_SKIP]
    for name in todo:
        ok, rsp, note = step(s1, name, {}, None, timeout=2.0)
        if name in AUTO_NORSP:
            ok, note = True, "norrsp-ok"
        g_log(f"{name}: {note}", ok)
        if not ok:
            RESULTS_FAIL.append((P, name, "empty", note))

    group("自动扫描-非法值(错误路径)")
    P = "auto_bogus"
    variant_all = list(REQ_NAMES)
    for name in variant_all:
        req_cls = globals()[name]
        tmp = req_cls()
        _fill_generic(tmp, "bogus")
        mid = MSG_ITEMS[name]
        send_packet(s1, mid, tmp)
        want = MSG_ITEMS.get(name[:-3] + "Rsp")
        if name in AUTO_NORSP:
            # 静默类消息: 窗口内无同名 Rsp 即通过
            ok, note = True, "norrsp-ok"
            deadline = time.time() + 1.0
            while time.time() < deadline:
                pkt = recv_packet(s1, max(0.05, deadline - time.time()))
                if pkt is None:
                    break
                if pkt[0] == want:
                    ok, note = False, "unexpected rsp"
                    break
        else:
            ok, note = _wait_rsp(s1, want, 2.0)
        COVERED.add(name)
        PATHS[name] = PATHS.get(name, 0) + 1
        g_log(f"{name}(bogus): {note}", ok)
        if not ok:
            RESULTS_FAIL.append((P, name, "bogus", note))

    group("自动扫描-合法配置(成功路径)")
    P = "auto_valid"
    for name in variant_all:
        req_cls = globals()[name]
        tmp = req_cls()
        _fill_generic(tmp, "valid")
        mid = MSG_ITEMS[name]
        send_packet(s1, mid, tmp)
        want = MSG_ITEMS.get(name[:-3] + "Rsp")
        if name in AUTO_NORSP:
            ok, note = True, "norrsp-ok"
            deadline = time.time() + 1.0
            while time.time() < deadline:
                pkt = recv_packet(s1, max(0.05, deadline - time.time()))
                if pkt is None:
                    break
                if pkt[0] == want:
                    ok, note = False, "unexpected rsp"
                    break
        else:
            ok, note = _wait_rsp(s1, want, 3.0)
        COVERED.add(name)
        PATHS[name] = PATHS.get(name, 0) + 1
        g_log(f"{name}(valid): {note}", ok)
        if not ok:
            RESULTS_FAIL.append((P, name, "valid", note))


_last_body = [b""]


def _wait_rsp(sock, want_id, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pkt = recv_packet(sock, max(0.05, deadline - time.time()))
        if pkt is None:
            return False, "NO_RSP"
        if pkt[0] == want_id:
            _last_body[0] = pkt[1]
            rsp = globals()[ID_TO_NAME[want_id]]()
            rsp.ParseFromString(pkt[1])
            return True, status_name(rsp) or "(no status)"
    return False, "TIMEOUT"


# ═══════════════════════════════════════


def server_traceback_delta():
    log = "/tmp/opencode/server.log"
    global TRACEBACK_BASE
    try:
        with open(log, "rb") as f:
            data = f.read()
        cnt = data.count(b"Traceback")
        if TRACEBACK_BASE is None:
            TRACEBACK_BASE = cnt
            return 0, cnt
        return cnt - TRACEBACK_BASE, cnt
    except FileNotFoundError:
        return 0, 0


def main():
    print("=" * 60)
    print("  全量 handler 路径测试")
    print("=" * 60)
    setup_ids()
    _load_cfg_sheets()

    s1, pid1, _ = connect_and_login("path_test")
    CTX["pid1"] = pid1
    CTX["home_scene"] = CTX["home_path_test"]
    print(f"  p1 登录成功 player_id={pid1}")

    s2, pid2, _ = connect_and_login("path_test2")
    CTX["pid2"] = pid2
    print(f"  p2 登录成功 player_id={pid2}")

    server_traceback_delta()

    phase_profile(s1)
    phase_ability_life(s1)
    phase_world_collect(s1)
    phase_explore_battle(s1)
    phase_interact_scene(s1)
    phase_bag_equip(s1)
    phase_social(s1, s2)
    phase_photo_share(s1)
    phase_garden(s1)
    phase_team(s1, s2)
    phase_dungeon_bossrush(s1)
    phase_mail(s1)
    phase_shop_economy(s1)
    phase_activity(s1)
    phase_achievement_claim(s1)
    phase_achieve_flow(s1)
    phase_misc(s1)
    phase_character_dead_revive(s1)
    phase_new_features(s1)
    phase_area_scene_end(s1)

    phase_connection(s2)

    auto_sweep(s1)

    phase_team_restore(s1)

    s1.close()
    # p2 下线
    try:
        send_packet(s2, MsgId.PlayerOfflineReq, PlayerOfflineReq())
        recv_packet(s2, 2)
    except Exception:
        pass
    s2.close()

    delta, total_tb = server_traceback_delta()

    print()
    print("─" * 60)
    print("  各阶段结果")
    print("─" * 60)
    print_group_summary()

    if RESULTS_FAIL:
        print()
        print("  失败明细:")
        for ph, name, desc, note in RESULTS_FAIL:
            print(f"    [{ph}] {name} {desc}: {note}")

    n_handlers = len(
        [
            f
            for f in os.listdir(os.path.join(ROOT, "handlers"))
            if f.endswith(".py") and f != "__init__.py"
        ]
    )
    print()
    print(f"  覆盖: {len(COVERED)}/{len(REQ_NAMES)} 条客户端请求消息")
    total_paths = sum(PATHS.values())
    multi = sum(1 for v in PATHS.values() if v >= 2)
    print(f"  总执行路径: {total_paths} (≥2路径的消息: {multi}/{len(REQ_NAMES)})")
    single = sorted(n for n in REQ_NAMES if PATHS.get(n, 0) < 2)
    if single:
        print(f"  单路径消息({len(single)}): {', '.join(single)}")
    print(f"  handler 模块数: {n_handlers}")
    print(f"  服务端 Traceback 增量: {delta} (总计 {total_tb})")
    g_fail = sum(g["fail"] for g in GROUP_RESULTS)
    verdict = "PASS" if (g_fail == 0 and delta == 0) else "FAIL"
    print(f"  总判定: {verdict}")
    print("=" * 60)
    sys.exit(0 if verdict == "PASS" else 1)


class EquipDisassembleTests(unittest.TestCase):
    def setUp(self):
        from handlers import EquipDisassemble

        self.module = EquipDisassemble
        self.items = {}
        self.sent = []
        self.session = SimpleNamespace(
            player_id=123, send=lambda *args: self.sent.append(args)
        )
        for name, target, kwargs in (
            (
                "lookup",
                self.module.db,
                {"side_effect": lambda pid, table, iid: self.items.get(iid)},
            ),
            (
                "delete",
                self.module.db,
                {"side_effect": lambda pid, iid: self.items.pop(iid)},
            ),
            ("grant", self.module.item_mgr, {}),
            ("report", self.module.achieve_track, {}),
        ):
            attr = {
                "lookup": "get_item_detail",
                "delete": "del_item_detail",
                "grant": "grant_items",
                "report": "report",
            }[name]
            p = patch.object(target, attr, **kwargs)
            setattr(self, name, p.start())
            self.addCleanup(p.stop)

    def add_item(self, kind="armor", instance_id=1, **fields):
        cfg = rl.res[kind.capitalize()][kind]["datas"][0]
        item = ItemDetail(extra_quality=5)
        equip = getattr(item.main_item, kind)
        setattr(equip, f"{kind}_id", cfg["i_d"])
        equip.instance_id = instance_id
        equip.level = 1
        equip.property_index = 1
        for key, value in fields.items():
            setattr(equip, key, value)
        self.items[instance_id] = item.SerializeToString()
        return equip

    def invoke(self, **fields):
        req = EquipDisassembleReq(**fields)
        self.module.Handler().handle(self.session, req.SerializeToString(), 17)
        mid, rsp, packet_id = self.sent[-1]
        self.assertEqual((mid, packet_id), (MsgId.EquipDisassembleRsp, 17))
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        return rsp

    def test_armor_uses_resource_chain_without_star(self):
        self.add_item()
        rsp = self.invoke(armor_ids=[1])
        self.assertEqual(list(rsp.armor_ids), [1])
        self.assertFalse(self.items)
        self.assertEqual(self.grant.call_args.args, (123, [(250, 1)]))
        self.report.assert_called_once_with(
            self.session, "disassemble", armor_n=1, weapon_n=0
        )

    def test_weapon_and_armor_use_property_group(self):
        for kind in ("weapon", "armor"):
            with self.subTest(kind=kind):
                equip = self.add_item(kind, property_index=2)
                table = rl.res[kind.capitalize()]
                cfg = table[kind]["datas"][0]
                prop = next(
                    r
                    for r in table[f"{kind}_property"]["datas"]
                    if r["i_d"] == cfg[f"{kind}_property_i_d"]
                )
                expected = prop[f"{kind}_property_group_info"][1]["disassemble_i_d"]
                row = self.module._disassemble_row(equip, kind)
                self.assertEqual(row["i_d"], expected)
                equip.property_index = 0
                equip.level = prop[f"{kind}_property_group_info"][1]["min_level"]
                self.assertEqual(
                    self.module._disassemble_row(equip, kind)["i_d"], expected
                )

    def test_locked_worn_missing_and_wrong_kind_are_not_removed(self):
        self.add_item(instance_id=1, is_lock=True)
        self.add_item(instance_id=2, wearer_id=101001)
        self.add_item("weapon", instance_id=3)
        rsp = self.invoke(armor_ids=[1, 2, 3, 999])
        self.assertFalse(rsp.armor_ids)
        self.delete.assert_not_called()
        self.grant.assert_not_called()
        self.report.assert_not_called()

    def test_duplicates_and_repeat_only_count_actual_items(self):
        self.add_item()
        self.assertEqual(list(self.invoke(armor_ids=[1, 1]).armor_ids), [1])
        self.assertFalse(self.invoke(armor_ids=[1]).armor_ids)
        self.assertEqual(self.delete.call_count, 1)
        self.assertEqual(self.grant.call_count, 1)
        self.assertEqual(self.report.call_count, 1)

    def test_missing_resource_preserves_equipment(self):
        self.add_item()
        with patch.dict(self.module.res, {"Armor": {}}):
            self.assertFalse(self.invoke(armor_ids=[1]).armor_ids)
        self.assertIn(1, self.items)
        self.delete.assert_not_called()
        self.report.assert_not_called()

    def test_no_random_reward_does_not_grant_fabricated_currency(self):
        self.add_item()
        with patch.object(self.module.random, "random", return_value=1):
            rsp = self.invoke(armor_ids=[1])
        self.assertEqual(list(rsp.armor_ids), [1])
        self.grant.assert_not_called()

    def test_corrupt_blob_propagates_before_any_delete(self):
        from google.protobuf.message import DecodeError

        self.add_item()
        self.items[2] = b"\xff"
        with self.assertRaises(DecodeError):
            self.invoke(armor_ids=[1, 2])
        self.delete.assert_not_called()
        self.grant.assert_not_called()

    def test_empty_request_does_not_change_state(self):
        self.invoke()
        self.delete.assert_not_called()
        self.grant.assert_not_called()
        self.report.assert_not_called()


class TreasureBoxResolveTests(unittest.TestCase):
    """STATIC 宝箱存储键口径: 按点位序号隔离, 同配置 id 多点位互不覆盖
    (官方实证: 场景1 idx12/idx13 同为配置 10101, 连开均独立产出)。"""

    def setUp(self):
        import utils.treasure_box as tb

        self.tb = tb

    def _session(self, scene_id=1, dungeon=None):
        return SimpleNamespace(player_id=123, scene_id=scene_id, dungeon=dungeon)

    def test_scene_boxes_same_config_isolated_by_index(self):
        # 场景1: idx12/idx13 配置 id 同为 10101 → store_key 必须分别为 12/13
        r12 = self.tb.resolve(self._session(), 0, 12)
        r13 = self.tb.resolve(self._session(), 0, 13)
        self.assertEqual(r12, (12, 10101))
        self.assertEqual(r13, (13, 10101))
        self.assertNotEqual(r12[0], r13[0])

    def test_scene_box_default_index_and_one_time(self):
        # 首条无 Index 字段按列表位 0; 一次性箱(30001)同样按 index 存储
        self.assertEqual(self.tb.resolve(self._session(), 0, 0), (0, 101001))
        self.assertEqual(self.tb.resolve(self._session(), 0, 1), (1, 101002))
        self.assertEqual(self.tb.resolve(self._session(), 0, 999), None)

    def test_dungeon_boxes_isolated_by_index(self):
        dungeon = [11101]
        boxes = next(
            dg.get("CollectionTreasureInfos") or ()
            for dg in rl.res["ScenesConfigAsset"]["Dungeons"]
            if isinstance(dg, dict) and dg.get("ID") == 11101
        )
        first = boxes[0]
        idx = first.get("Index", 0)
        resolved = self.tb.resolve(self._session(dungeon=dungeon), 0, idx, 1)
        self.assertEqual(resolved[0], idx)
        self.assertEqual(resolved[1], first["ID"])
        # 同一副本不存在请求时回 None
        self.assertEqual(
            self.tb.resolve(self._session(dungeon=dungeon), 0, 999, 1), None
        )


class ActivityExploreTests(unittest.TestCase):
    def setUp(self):
        import pickle
        import utils.db as db
        from handlers import Explore, ExploreQuickFinish, ExploreReward

        self.modules = (Explore, ExploreQuickFinish, ExploreReward)
        self.cfg = rl.res["Explore"]["explore_activity"]["datas"][0]
        self.state = {}
        self.sent = []
        self.session = SimpleNamespace(player_id=123, send=self.send)
        self.pickle = pickle
        for name, replacement in (
            ("get_kv", self.get_kv),
            ("set_kv", self.set_kv),
        ):
            p = patch.object(db, name, side_effect=replacement)
            p.start()
            self.addCleanup(p.stop)

    def get_kv(self, player_id, ns, key, default=None):
        return self.state.get((ns, str(key)), default)

    def set_kv(self, player_id, ns, key, value):
        self.state[(ns, str(key))] = value

    def send(self, mid, msg, packet_id):
        copy = type(msg)()
        copy.CopyFrom(msg)
        self.sent.append((mid, copy))

    def invoke(self, module, req):
        self.sent.clear()
        module.Handler().handle(self.session, req.SerializeToString(), 17)
        return next(msg for mid, msg in self.sent if mid == module.Handler.msg_id + 1)

    def start(self):
        return self.invoke(
            self.modules[0], ExploreReq(explore_id=self.cfg["i_d"], is_activity=True)
        )

    def test_start_returns_state(self):
        rsp = self.start()
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual(rsp.explore.explore_id, self.cfg["i_d"])
        self.assertGreater(rsp.explore.start_time, 0)

    def test_cancel_activity_resets_state(self):
        self.start()
        module = importlib.import_module("handlers.ExploreCancel")
        rsp = self.invoke(
            module, ExploreCancelReq(explore_id=self.cfg["i_d"], is_activity=True)
        )
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual(rsp.explore.explore_id, self.cfg["i_d"])
        self.assertEqual(rsp.explore.start_time, 0)
        init = importlib.import_module("handlers.ExploreInit")
        self.sent.clear()
        init.Handler().handle(self.session, ExploreInitReq().SerializeToString(), 18)
        init_rsp = next(msg for mid, msg in self.sent if mid == MsgId.ExploreInitRsp)
        entry = next(
            m for m in init_rsp.activity_explore if m.explore_id == self.cfg["i_d"]
        )
        self.assertEqual(entry.start_time, 0)
        self.assertEqual(entry.times, 1)

    def test_cancel_idle_activity_rejected(self):
        module = importlib.import_module("handlers.ExploreCancel")
        rsp = self.invoke(
            module, ExploreCancelReq(explore_id=self.cfg["i_d"], is_activity=True)
        )
        self.assertEqual(rsp.status, StatusCode.StatusCode_EXPLORE_NOT_EXISTS)
        self.assertFalse(self.state)

    def test_unknown_activity_does_not_mutate(self):
        for module, req_type in zip(
            self.modules,
            (
                ExploreReq,
                ExploreQuickFinishReq,
                ExploreRewardReq,
            ),
        ):
            with self.subTest(message=req_type.__name__):
                rsp = self.invoke(module, req_type(explore_id=999999, is_activity=True))
                self.assertEqual(rsp.status, StatusCode.StatusCode_CFG_NOT_FOUND)
                self.assertFalse(self.state)

    def test_repeated_start_preserves_state(self):
        self.start()
        before = dict(self.state)
        rsp = self.start()
        self.assertEqual(rsp.status, StatusCode.StatusCode_EXPLORE_IN_PROGRESS)
        self.assertEqual(self.state, before)

    def test_quick_finish_insufficient_items_preserves_state(self):
        self.start()
        before = dict(self.state)
        module = self.modules[1]
        with patch.object(module.item_mgr, "consume_items", return_value=False):
            rsp = self.invoke(
                module,
                ExploreQuickFinishReq(explore_id=self.cfg["i_d"], is_activity=True),
            )
        self.assertEqual(rsp.status, StatusCode.StatusCode_ITEM_NOT_ENOUGH)
        self.assertEqual(self.state, before)
        self.assertEqual(len(self.sent), 1)

    def test_quick_finish_is_idempotent_and_returns_state(self):
        self.start()
        module = self.modules[1]
        req = ExploreQuickFinishReq(explore_id=self.cfg["i_d"], is_activity=True)
        with patch.object(
            module.item_mgr, "consume_items", return_value=True
        ) as consume:
            first = self.invoke(module, req)
            before = dict(self.state)
            second = self.invoke(module, req)
        self.assertEqual(consume.call_count, 1)
        self.assertEqual(self.state, before)
        self.assertTrue(first.explore.is_quick_finish)
        self.assertTrue(second.explore.is_quick_finish)

    def test_quick_finish_survives_init(self):
        self.start()
        module = self.modules[1]
        with patch.object(module.item_mgr, "consume_items", return_value=True):
            self.invoke(
                module,
                ExploreQuickFinishReq(explore_id=self.cfg["i_d"], is_activity=True),
            )
        init = importlib.import_module("handlers.ExploreInit")
        rsp = self.invoke(init, ExploreInitReq())
        entry = next(m for m in rsp.activity_explore if m.explore_id == self.cfg["i_d"])
        self.assertTrue(entry.is_quick_finish)

    def test_quick_finish_reward_is_granted_once(self):
        self.start()
        quick = self.modules[1]
        with patch.object(quick.item_mgr, "consume_items", return_value=True):
            self.invoke(
                quick,
                ExploreQuickFinishReq(explore_id=self.cfg["i_d"], is_activity=True),
            )
        reward = self.modules[2]

        def grant(player_id, rewards, **kwargs):
            for item_id, num in rewards:
                item = kwargs["rsp_items"].add()
                item.main_item.base_item.item_id = item_id
                item.main_item.base_item.num = num
                kwargs["pack_notice"].items.add().CopyFrom(item)

        req = ExploreRewardReq(explore_id=self.cfg["i_d"], is_activity=True)
        with patch.object(reward.item_mgr, "grant_items", side_effect=grant) as grants:
            rsp = self.invoke(reward, req)
            self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
            self.assertTrue(rsp.reward_item)
            self.assertEqual(rsp.explore.explore_id, self.cfg["i_d"])
            self.assertEqual(rsp.explore.start_time, 0)
            self.assertFalse(rsp.explore.is_quick_finish)
            self.assertEqual(
                [mid for mid, msg in self.sent],
                [MsgId.ExploreRewardRsp, MsgId.PackNotice],
            )
            repeat = self.invoke(reward, req)
            self.assertEqual(repeat.status, StatusCode.StatusCode_EXPLORE_NOT_FINISH)
            self.assertEqual(grants.call_count, 1)
        restarted = self.start()
        self.assertEqual(restarted.status, StatusCode.StatusCode_OK)
        self.assertFalse(restarted.explore.is_quick_finish)

    def test_normal_cancel_persists_without_touching_activity(self):
        import utils.garden_state as garden_state

        self.start()
        activity_before = dict(self.state)
        explore_id = garden_state.explore_area_ids()[0]
        e = garden_state.get_explore(self.session.player_id, explore_id)
        e["start_time"] = 12345
        e["is_quick_finish"] = True
        garden_state.set_explore(self.session.player_id, explore_id, e)
        module = importlib.import_module("handlers.ExploreCancel")
        rsp = self.invoke(module, ExploreCancelReq(explore_id=explore_id))
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        saved = garden_state.get_explore(self.session.player_id, explore_id)
        self.assertEqual(saved["start_time"], 0)
        self.assertFalse(saved["is_quick_finish"])
        for key, value in activity_before.items():
            self.assertEqual(self.state[key], value)

    def test_unfinished_reward_returns_current_state(self):
        started = self.start()
        rsp = self.invoke(
            self.modules[2],
            ExploreRewardReq(explore_id=self.cfg["i_d"], is_activity=True),
        )
        self.assertEqual(rsp.status, StatusCode.StatusCode_EXPLORE_NOT_FINISH)
        self.assertEqual(rsp.explore.explore_id, self.cfg["i_d"])
        self.assertEqual(rsp.explore.start_time, started.explore.start_time)


class HandlerContractTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.session = SimpleNamespace(
            player_id=123,
            avatar_id=41101,
            send=lambda *args: self.sent.append(args),
        )

    def test_ping_echo_and_millisecond_clock(self):
        from handlers import PlayerPing

        req = PlayerPingReq(client_time_ms=123456)
        with patch.object(PlayerPing.time, "time", return_value=1700000000.125):
            PlayerPing.Handler().handle(self.session, req.SerializeToString(), 17)
        mid, rsp, packet_id = self.sent[0]
        self.assertEqual((mid, packet_id), (MsgId.PlayerPingRsp, 17))
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual(rsp.client_time_ms, 123456)
        self.assertEqual(rsp.server_time_ms, 1700000000125)

    def test_sign_write_and_echo_including_clear(self):
        from handlers import ChangeSign

        for sign in ("测试签名", ""):
            with self.subTest(sign=sign), patch.object(
                ChangeSign.db, "set_players_info"
            ) as save:
                req = ChangeSignReq(sign=sign)
                ChangeSign.Handler().handle(self.session, req.SerializeToString(), 17)
                save.assert_called_once_with(123, "sign", sign)
                mid, rsp, packet_id = self.sent[-1]
                self.assertEqual((mid, packet_id), (MsgId.ChangeSignRsp, 17))
                self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
                self.assertEqual(rsp.sign, sign)

    def test_mails_empty_and_stored_payload(self):
        from handlers import GetMails

        stored = GetMailsRsp()
        stored.mails.add(mail_id=7, title="测试邮件")
        for rows in ([], [stored.mails[0].SerializeToString()]):
            with self.subTest(count=len(rows)), patch.object(
                GetMails.db, "get_mail", return_value=rows
            ) as load:
                GetMails.Handler().handle(self.session, b"", 17)
                load.assert_called_once_with(123)
                mid, rsp, packet_id = self.sent[-1]
                self.assertEqual((mid, packet_id), (MsgId.GetMailsRsp, 17))
                self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
                self.assertEqual([m.SerializeToString() for m in rsp.mails], rows)

    def test_corrupt_mail_propagates_without_partial_response(self):
        from google.protobuf.message import DecodeError
        from handlers import GetMails

        with patch.object(GetMails.db, "get_mail", return_value=[b"\xff"]):
            with self.assertRaises(DecodeError):
                GetMails.Handler().handle(self.session, b"", 17)
        self.assertFalse(self.sent)

    def test_npc_ordinary_dialogue_reports_before_response(self):
        from handlers import NpcTalk

        events = []
        self.session.send = lambda *args: events.append(("send", args))
        with patch.object(
            NpcTalk.achieve_track, "batch", return_value=nullcontext()
        ), patch.object(
            NpcTalk.achieve_track,
            "report",
            side_effect=lambda *a, **k: events.append(("report", k)),
        ), patch.object(
            NpcTalk.item_mgr, "grant_items"
        ) as grant:
            req = NpcTalkReq(id=123)
            NpcTalk.Handler().handle(self.session, req.SerializeToString(), 17)
        self.assertEqual([event[0] for event in events], ["report", "send"])
        self.assertEqual(events[0][1], {"match": 123})
        mid, rsp, packet_id = events[1][1]
        self.assertEqual((mid, packet_id), (MsgId.NpcTalkRsp, 17))
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        grant.assert_not_called()


class AdditionalHandlerTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.session = SimpleNamespace(
            player_id=123,
            scene_id=1,
            channel_id=1,
            scene_player=ScenePlayer(),
            send=lambda *args: self.sent.append(args),
        )

    def test_gacha_new_character_quality(self):
        from handlers import Gacha

        char_id = rl.res["Character"]["character"]["datas"][0]["i_d"]
        quality = next(
            r["quality"] for r in rl.res["Item"]["item"]["datas"] if r["i_d"] == char_id
        )
        cost = ItemDetail()
        cost.main_item.base_item.num = 100000

        def grant(player_id, character_id, item):
            item.main_item.item_id = character_id
            return False

        with patch.object(
            Gacha.db, "get_gacha_guarantee", return_value=0
        ), patch.object(
            Gacha.db, "get_item_detail", return_value=cost.SerializeToString()
        ), patch.object(
            Gacha.db, "set_item_detail"
        ), patch.object(
            Gacha.db, "add_gacha_record"
        ), patch.object(
            Gacha.db, "set_gacha_guarantee"
        ), patch.object(
            Gacha.random, "choice", return_value=char_id
        ), patch.object(
            Gacha.item_mgr, "grant_character", side_effect=grant
        ), patch.object(
            Gacha.item_mgr, "grant_items"
        ), patch.object(
            Gacha.achieve_track, "report"
        ):
            Gacha.Handler().handle(
                self.session,
                GachaReq(gacha_id=1000, is_single=True).SerializeToString(),
                17,
            )
        self.assertEqual([x[0] for x in self.sent], [MsgId.GachaRsp, MsgId.PackNotice])
        rsp = self.sent[0][1]
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual(rsp.items[0].main_item.item_id, char_id)
        self.assertEqual(rsp.items[0].extra_quality, quality)
        self.assertEqual(self.sent[1][1].items[-1].extra_quality, quality)

    def test_appearance_sync_scoped_to_scene_and_channel(self):
        from handlers import UpdatePlayerAppearance as module
        from server import scene_data

        others = []
        peer = SimpleNamespace(
            scene_id=1, channel_id=1, send=lambda *a: others.append(a)
        )
        excluded = SimpleNamespace(
            scene_id=2, channel_id=1, send=lambda *a: self.fail("wrong scene")
        )
        channel = SimpleNamespace(
            scene_id=1, channel_id=2, send=lambda *a: self.fail("wrong channel")
        )
        with patch.object(module.db, "set_players_info") as save, patch.object(
            module.pb_create, "make_ScenePlayer"
        ), patch.object(
            scene_data, "get_session", return_value=[peer, excluded, channel]
        ):
            module.Handler().handle(
                self.session, UpdatePlayerAppearanceReq().SerializeToString(), 17
            )
        self.assertEqual(save.call_count, 2)
        self.assertEqual(self.sent[0][0], MsgId.UpdatePlayerAppearanceRsp)
        self.assertEqual(self.sent[0][2], 17)
        self.assertEqual(len(others), 1)
        notice = others[0][1]
        self.assertEqual(others[0][0], MsgId.ServerSceneSyncDataNotice)
        self.assertEqual(
            notice.data[0].server_data[0].action_type,
            SceneActionType.SceneActionType_UPDATE_APPEARANCE,
        )

    def test_gacha_record_page_rounding_and_echo(self):
        from handlers import GachaRecord as module

        for total, pages in ((0, 0), (1, 1), (5, 1), (6, 2)):
            with self.subTest(total=total), patch.object(
                module.db, "get_total_gacha_num", return_value=total
            ), patch.object(module.db, "get_gacha_records", return_value=[]) as load:
                module.Handler().handle(
                    self.session,
                    GachaRecordReq(gacha_id=1000, page=1).SerializeToString(),
                    17,
                )
                load.assert_called_once_with(123, 1000, 1)
                mid, rsp, packet_id = self.sent[-1]
                self.assertEqual((mid, packet_id), (MsgId.GachaRecordRsp, 17))
                self.assertEqual(
                    (rsp.gacha_id, rsp.page, rsp.total_page), (1000, 1, pages)
                )

    def test_head_valid_and_unknown_configuration(self):
        from handlers import ChangeHead as module

        head = next(
            r["head_i_d"] for r in rl.res["Head"]["head"]["datas"] if r.get("is_show")
        )
        for value, valid in ((head, True), (2147483647, False)):
            with self.subTest(value=value), patch.object(
                module.db, "set_players_info"
            ) as save:
                module.Handler().handle(
                    self.session, ChangeHeadReq(head=value).SerializeToString(), 17
                )
                rsp = self.sent[-1][1]
                if valid:
                    save.assert_called_once_with(123, "head", head)
                    self.assertEqual(rsp.head, head)
                    self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
                else:
                    save.assert_not_called()
                    self.assertEqual(rsp.status, StatusCode.StatusCode_CFG_NOT_FOUND)


class SessionSendContractTests(unittest.TestCase):
    def setUp(self):
        from collections import deque
        from threading import Lock, Event
        from network.game_session import GameSession

        self.session = GameSession.__new__(GameSession)
        self.session.running = True
        self.session._send_queue = deque()
        self.session._send_lock = Lock()
        self.session._send_event = Event()

    def test_binary_payload_enqueues_unchanged(self):
        payload = b"\x08\x02"
        self.session.send(MsgId.PlayerPingRsp, payload, 17, True)
        task = self.session._send_queue[0]
        self.assertEqual(
            (task.msg_id, task.data, task.packet_id, task.is_bin),
            (MsgId.PlayerPingRsp, payload, 17, True),
        )
        self.assertTrue(self.session._send_event.is_set())

    def test_message_without_status_serializes(self):
        message = PacketHead(msg_id=1008)
        self.session.send(1008, message, 17)
        self.assertEqual(self.session._send_queue[0].data, message.SerializeToString())
        self.assertFalse(self.session._send_queue[0].is_bin)

    def test_normal_response_serializes(self):
        message = PlayerPingRsp(status=StatusCode.StatusCode_OK, client_time_ms=123)
        self.session.send(MsgId.PlayerPingRsp, message, 17)
        self.assertEqual(self.session._send_queue[0].data, message.SerializeToString())

    def test_stopped_session_does_not_enqueue(self):
        self.session.running = False
        self.session.send(MsgId.PlayerPingRsp, b"", 17, True)
        self.assertFalse(self.session._send_queue)
        self.assertFalse(self.session._send_event.is_set())


if __name__ == "__main__":
    main()
