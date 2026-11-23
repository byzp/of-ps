from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetCharacterAchievementAwardReq,
    GetCharacterAchievementAwardRsp,
    StatusCode,
    Character,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res

"""
# 角色成就领奖(按档位 index) 1481 1482
档位奖励(已对表验证): Character.character_achieve_reward.achieve_reward_info
{num, u_i_index, unlock_item_i_d, unlock_item_count, reward_item_i_d,
reward_item_count, new_reward_price_type}, req.reward_index 对应 num
(1-8 免费档, 9-16 为 new_reward_price_type=1 的付费档, 需 is_unlock_payment);
如角色 101001 num=3 -> 金币x10000。
领取状态持久化在 Character.reward_index_lst(客户端展示用),
发奖去重另经 claimed_rewards(system='chr_achieve') db.try_claim 原子把关
(Character blob 的 check-then-set 本身不原子)
"""


@packet_handler(MsgId.GetCharacterAchievementAwardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCharacterAchievementAwardReq()
        req.ParseFromString(data)

        rsp = GetCharacterAchievementAwardRsp()
        rsp.character_id = req.character_id

        characters = db.get_characters(session.player_id, req.character_id)
        if not characters:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GetCharacterAchievementAwardRsp, rsp, packet_id)
            return

        # character_achieve_reward: i_d==character_id 的 achieve_reward_info
        # 中 num==req.reward_index 的档位配置
        cfg = None
        if (
            "Character" in res
            and "character_achieve_reward" in res["Character"]
            and "datas" in res["Character"]["character_achieve_reward"]
        ):
            for entry in res["Character"]["character_achieve_reward"]["datas"]:
                if entry["i_d"] == req.character_id:
                    for info in entry.get("achieve_reward_info", ()):
                        if info.get("num") == req.reward_index:
                            cfg = info
                            break
                    break
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GetCharacterAchievementAwardRsp, rsp, packet_id)
            return

        chr = Character()
        chr.ParseFromString(characters[0])

        # 付费档(new_reward_price_type=1)需先付费解锁
        if cfg.get("new_reward_price_type") and not chr.is_unlock_payment:
            rsp.status = StatusCode.StatusCode_FAIL
            rsp.rewarded_index_lst.extend(chr.reward_index_lst)
            session.send(MsgId.GetCharacterAchievementAwardRsp, rsp, packet_id)
            return

        if req.reward_index in chr.reward_index_lst or not db.try_claim(
            session.player_id, "chr_achieve", f"{req.character_id}:{req.reward_index}"
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            rsp.rewarded_index_lst.extend(chr.reward_index_lst)
            session.send(MsgId.GetCharacterAchievementAwardRsp, rsp, packet_id)
            return

        chr.reward_index_lst.append(req.reward_index)
        db.set_character(session.player_id, req.character_id, chr.SerializeToString())

        rsp.status = StatusCode.StatusCode_OK
        rsp.rewarded_index_lst.extend(chr.reward_index_lst)
        # achieve_reward_info.reward_item_i_d x reward_item_count
        item_mgr.grant_items(
            session.player_id,
            [(cfg.get("reward_item_i_d", 0), cfg.get("reward_item_count", 1))],
            rsp_items=rsp.items,
            session=session,
        )

        session.send(MsgId.GetCharacterAchievementAwardRsp, rsp, packet_id)  # 1481,1482
