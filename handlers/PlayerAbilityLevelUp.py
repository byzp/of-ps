from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PlayerAbilityLevelUpReq,
    PlayerAbilityLevelUpRsp,
    StatusCode,
    PackNotice,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils import achieve_track

"""
# 玩家能力升级 1613 1614
消耗配置(已对表验证): Ability.ability{i_d, need_item_i_d, level_info}
level_info: [{level, cost_item_i_d, cost_count, reward_item_i_d}, ...]
升到 level N 扣 cost_item_i_d x cost_count(如 ability 1010 升1级 -> 水晶103 x10),
超出 level_info 最高级返回 ABILITY_LEVEL_LIMIT。
等级持久化: kv ns=ability, k=ability_id, v=level(PlayerAbilityList 读同一处)。
"""


@packet_handler(MsgId.PlayerAbilityLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerAbilityLevelUpReq()
        req.ParseFromString(data)

        rsp = PlayerAbilityLevelUpRsp()

        # Ability.ability 配置
        level_info = None
        for a in res.get("Ability", {}).get("ability", {}).get("datas", ()) or ():
            if a["i_d"] == req.ability_id:
                level_info = a.get("level_info", ())
                break
        if level_info is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.PlayerAbilityLevelUpRsp, rsp, packet_id)
            return

        cur_level = int(db.get_kv(session.player_id, "ability", req.ability_id, 0) or 0)
        new_level = cur_level + 1

        # 目标等级的消耗条目; 超出配置最高级则禁止升级
        cost_cfg = None
        for info in level_info:
            if info.get("level") == new_level:
                cost_cfg = info
                break
        if cost_cfg is None:
            rsp.status = StatusCode.StatusCode_ABILITY_LEVEL_LIMIT
            rsp.ability.ability_id = req.ability_id
            rsp.ability.level = cur_level
            session.send(MsgId.PlayerAbilityLevelUpRsp, rsp, packet_id)
            return

        # 扣除升级消耗 level_info.cost_item_i_d x cost_count
        cost_item = cost_cfg.get("cost_item_i_d", 0)
        cost_count = cost_cfg.get("cost_count", 0)
        costs = [(cost_item, cost_count)] if cost_item and cost_count else []
        previous = next(
            (info for info in level_info if info.get("level") == cur_level), None
        )
        if previous and previous.get("reward_item_i_d"):
            # 等级效果互相替换，不能把1级与2级的数值道具同时留在背包。
            costs.append((previous["reward_item_i_d"], 1))
        notice = None
        if costs:
            notice = PackNotice()
            notice.status = StatusCode.StatusCode_OK
            if not item_mgr.consume_items(
                session.player_id,
                costs,
                pack_notice=notice,
                session=session,
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                rsp.ability.ability_id = req.ability_id
                rsp.ability.level = cur_level
                session.send(MsgId.PlayerAbilityLevelUpRsp, rsp, packet_id)
                return
            for detail in notice.items:
                rsp.items.add().CopyFrom(detail)

        db.set_kv(session.player_id, "ability", req.ability_id, new_level)
        # 成就138: 使用水晶提升能力。
        achieve_track.report(session, "ability_level_up")

        rsp.status = StatusCode.StatusCode_OK
        rsp.ability.ability_id = req.ability_id
        rsp.ability.level = new_level

        # 等级只是展示进度；真正的能力数值来自该等级reward_item_i_d。
        if cost_cfg.get("reward_item_i_d"):
            if notice is None:
                notice = PackNotice(status=StatusCode.StatusCode_OK)
            item_mgr.grant_items(
                session.player_id,
                [(cost_cfg["reward_item_i_d"], 1)],
                rsp_items=rsp.items,
                pack_notice=notice,
                session=session,
            )

        session.send(MsgId.PlayerAbilityLevelUpRsp, rsp, packet_id)  # 1613,1614
        if notice is not None and notice.items:
            session.send(MsgId.PackNotice, notice, 0)
