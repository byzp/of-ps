from config import Config
from proto.net_pb2 import LifeSkillLevelUpNotice

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import time

from proto.net_pb2 import (
    LifeSkillLevelUpReq,
    LifeSkillLevelUpRsp,
    StatusCode,
    LifeBaseInfo,
    ItemDetail,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils import item_mgr as items_util
from utils import achieve_track

# 成就: 学习生活技能类型映射已移入 achieve_track(事件 learn_life_skill)


def _skill_cfg(life_type, skill_id):
    """返回 (逐级条目 tuple, 生活等级需求键, 材料键); 表/技能缺失返回 (None, ...)"""
    m = Config.LIFE_SKILL_LEVEL_UP_SKILL_TABLES.get(life_type)
    if not m:
        return None, None, None
    fname, tname, items_key, lv_key, need_key = m
    for e in res.get(fname, {}).get(tname, {}).get("datas") or ():
        if e.get("i_d") == skill_id:
            return e.get(items_key, ()), lv_key, need_key
    return (), lv_key, need_key


def _life_level(player_id, life_type):
    life_blob = db.get_life(player_id, life_type)
    if life_blob:
        info = LifeBaseInfo()
        info.ParseFromString(life_blob)
        return max(info.level, 1)
    return 1


@packet_handler(MsgId.LifeSkillLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = LifeSkillLevelUpReq()
        req.ParseFromString(data)

        rsp = LifeSkillLevelUpRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.is_force_study = req.is_force_study

        now = int(time.time())

        def fail(code):
            rsp.status = code
            session.send(MsgId.LifeSkillLevelUpRsp, rsp, packet_id)  # 1393,1394
            return

        levels, lv_key, need_key = _skill_cfg(req.life_type, req.skill_id)

        skills = db.get_life_skills(session.player_id, req.life_type)
        lv, start_time = skills.get(req.skill_id, (0, 0))

        cfg = None
        if levels is not None:
            if not levels:
                fail(StatusCode.StatusCode_PlayerLifeSkillNotExist)
                return
            max_lv = max(e.get("level", 0) for e in levels)
            if lv >= max_lv:
                fail(StatusCode.StatusCode_LifeSkillMaxLv)
                return
            for e in levels:
                if e.get("level") == lv + 1:
                    cfg = e
                    break
            if cfg is None:
                fail(StatusCode.StatusCode_CFG_NOT_FOUND)
                return
            # 生活等级需求(need_cook_level 等)
            if cfg.get(lv_key, 0) > _life_level(session.player_id, req.life_type):
                fail(StatusCode.StatusCode_LifeLvNotEnough)
                return
            # 上一级仍在学习中(start_study_time + 上一级 need_time 未到)时,
            # 非强制学习不可继续
            if lv >= 1 and not req.is_force_study:
                prev_time = 0
                for e in levels:
                    if e.get("level") == lv:
                        prev_time = e.get("need_time", 0)
                        break
                if start_time and now < start_time + prev_time:
                    fail(StatusCode.StatusCode_SkillAlreadyStudy)
                    return
            # 汇总消耗: need_currency + *_need_item 材料(原子扣除)
            needs = {}
            if cfg.get("need_currency_i_d"):
                needs[cfg["need_currency_i_d"]] = cfg.get("need_currency_count", 0)
            if need_key:
                for m in cfg.get(need_key, ()):
                    if m.get("need_item_i_d"):
                        needs[m["need_item_i_d"]] = needs.get(
                            m["need_item_i_d"], 0
                        ) + m.get("need_item_count", 0)
            if needs:
                # 先校验(避免无意义的空扣除)
                for iid, cnt in needs.items():
                    if items_util.get_num(session.player_id, iid) < cnt:
                        fail(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                        return
                pack = PackNotice()
                pack.status = StatusCode.StatusCode_OK
                if not items_util.consume_items(
                    session.player_id,
                    list(needs.items()),
                    pack_notice=pack,
                    session=session,
                ):
                    fail(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                    return
                for it in pack.items:
                    rsp.items.add().CopyFrom(it)
                session.send(MsgId.PackNotice, pack, 0)

        skills = db.get_life_skills(session.player_id, req.life_type)
        lv, _ = skills.get(req.skill_id, (0, 0))
        lv += 1
        skills[req.skill_id] = (lv, now)
        db.set_life_skills(session.player_id, req.life_type, skills)

        rsp.life_skills.life_type = req.life_type
        skill = rsp.life_skills.life_skill_info.add()
        skill.skill_id = req.skill_id
        skill.lv = lv
        skill.start_study_time = now
        # 成就: 学习生活技能(类型由事件层按 life_type 归族)
        achieve_track.report(session, "learn_life_skill", life_type=req.life_type)
        session.send(MsgId.LifeSkillLevelUpRsp, rsp, packet_id)  # 1393,1394

        # 生活技能升级推送

        _n = LifeSkillLevelUpNotice()
        _n.status = StatusCode.StatusCode_OK
        _ls = _n.life_skills
        _ls.life_type = req.life_type
        _sk = _ls.life_skill_info.add()
        _sk.skill_id = req.skill_id
        _sk.lv = lv
        _sk.start_study_time = now
        session.send(MsgId.LifeSkillLevelUpNotice, _n, 0)
