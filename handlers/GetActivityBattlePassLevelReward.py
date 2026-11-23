from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetActivityBattlePassLevelRewardReq,
    GetActivityBattlePassLevelRewardRsp,
    StatusCode,
    PackNotice,
)
from utils.res_loader import res
import utils.db as db
from utils.activity_state import template_id


def _find_battle_pass(bp_id):
    """BattlePass.battle_pass 按 i_d 查找; 客户端可能传活动 id,
    此时经 Activity.activity(i_d → activity_i_d) 映射到战令 i_d"""
    datas = res.get("BattlePass", {}).get("battle_pass", {}).get("datas")
    if datas is None:
        return None
    for e in datas:
        if e.get("i_d") == template_id(bp_id):
            return e
    for a in res.get("Activity", {}).get("activity", {}).get("datas", ()) or ():
        if a.get("i_d") == bp_id and a.get("activity_i_d"):
            for e in datas:
                if e.get("i_d") == a["activity_i_d"]:
                    return e
    return None


@packet_handler(MsgId.GetActivityBattlePassLevelRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetActivityBattlePassLevelRewardReq()
        req.ParseFromString(data)

        rsp = GetActivityBattlePassLevelRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        # BattlePass.battle_pass.battle_pass_level_ups[level].battle_pass_reward
        # 每级固定两条 [{item_i_d,item_num}x2]: 第1条为免费奖励, 第2条为付费奖励
        bp = _find_battle_pass(req.activity_battle_pass_id)
        level_up = None
        if bp:
            for l in bp.get("battle_pass_level_ups", ()):
                if l.get("level") == req.level:
                    level_up = l
                    break
        if not level_up:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(
                MsgId.GetActivityBattlePassLevelRewardRsp, rsp, packet_id
            )  # 2133,2134
            return

        reward_cfgs = level_up.get("battle_pass_reward", ())
        idx = 0 if req.is_get_free_reward else 1
        reward_list = []
        if idx < len(reward_cfgs):
            r = reward_cfgs[idx]
            if r.get("item_i_d"):
                reward_list.append((r["item_i_d"], r.get("item_num", 1)))

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if not db.try_claim(
            session.player_id,
            "bp_level_reward",
            f"{req.activity_battle_pass_id}:{req.level}:{req.is_get_free_reward}",
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(
                MsgId.GetActivityBattlePassLevelRewardRsp, rsp, packet_id
            )  # 2133,2134
            return
        db.grant_rewards(session.player_id, reward_list, rsp.rewards, pack)

        session.send(
            MsgId.GetActivityBattlePassLevelRewardRsp, rsp, packet_id
        )  # 2133,2134
        session.send(MsgId.PackNotice, pack, 0)
