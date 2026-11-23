from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetCharacterAchievementBadgeAwardReq,
    GetCharacterAchievementBadgeAwardRsp,
    StatusCode,
    Character,
)

import utils.db as db
from utils import item_mgr

"""
# 角色成就徽章领奖 1485 1486
徽章奖励(已对表验证): Character.character_achieve.achieve_info
{achieve_i_d, item_i_d, item_count}, req.achievement_id 对应 achieve_i_d,
发放该角色纪念章(如角色 101001 achieve 41010010 -> 菲的纪念章 51101 x1)。
领取状态持久化在 Character.rewarded_achievement_id_lst(客户端展示用),
发奖去重另经 claimed_rewards(system='chr_badge') db.try_claim 原子把关
(Character blob 的 check-then-set 本身不原子)
"""


@packet_handler(MsgId.GetCharacterAchievementBadgeAwardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCharacterAchievementBadgeAwardReq()
        req.ParseFromString(data)

        rsp = GetCharacterAchievementBadgeAwardRsp()

        characters = db.get_characters(session.player_id, req.character_id)
        if not characters:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GetCharacterAchievementBadgeAwardRsp, rsp, packet_id)
            return

        # character_achieve.achieve_info 中 achieve_i_d 对应的徽章条目
        badge_cfg = None
        for entry in (
            db.get_character_achievement_lst(session.player_id, req.character_id) or []
        ):
            if (
                isinstance(entry, dict)
                and entry.get("achieve_i_d") == req.achievement_id
            ):
                badge_cfg = entry
                break
        if badge_cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GetCharacterAchievementBadgeAwardRsp, rsp, packet_id)
            return

        chr = Character()
        chr.ParseFromString(characters[0])
        if req.achievement_id in chr.rewarded_achievement_id_lst or not db.try_claim(
            session.player_id,
            "chr_badge",
            f"{req.character_id}:{req.achievement_id}",
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            rsp.rewarded_achievement_id_lst.extend(chr.rewarded_achievement_id_lst)
            session.send(MsgId.GetCharacterAchievementBadgeAwardRsp, rsp, packet_id)
            return

        chr.rewarded_achievement_id_lst.append(req.achievement_id)
        db.set_character(session.player_id, req.character_id, chr.SerializeToString())

        rsp.status = StatusCode.StatusCode_OK
        rsp.rewarded_achievement_id_lst.extend(chr.rewarded_achievement_id_lst)
        achieve_b = db.get_achieve(session.player_id, req.achievement_id)
        if achieve_b:
            rsp.achieves.add().ParseFromString(achieve_b)
        # achieve_info.item_i_d x item_count(该角色的纪念章)
        item_mgr.grant_items(
            session.player_id,
            [(badge_cfg.get("item_i_d", 0), badge_cfg.get("item_count", 1))],
            rsp_items=rsp.update_items,
            session=session,
        )

        session.send(
            MsgId.GetCharacterAchievementBadgeAwardRsp, rsp, packet_id
        )  # 1485,1486
