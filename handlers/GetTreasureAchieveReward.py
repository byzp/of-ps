from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetTreasureAchieveRewardReq,
    GetTreasureAchieveRewardRsp,
    StatusCode,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils.reward_resolver import resolve_reward
from utils import item_mgr

"""
# 领取考古成就奖励 4527 4528
# 配置: ArchaeologyAchieve.json archaeology_achieve
#   items: [{achieve_i_d, reward_i_d}], reward_i_d -> Reward.json
#   new_archaeology_type 对应 EArchaeologyType(缺省 0=Book)
领取状态持久化在 claimed_rewards 表(system='treasure_achieve'), db.try_claim 原子去重
"""


def get_achieve_reward_id(achieve_id):
    """按 achieve_i_d 查 ArchaeologyAchieve.json 的 reward_i_d"""
    for e in (
        res.get("ArchaeologyAchieve", {})
        .get("archaeology_achieve", {})
        .get("datas", ())
    ):
        for it in e.get("items", ()):
            if it.get("achieve_i_d") == achieve_id:
                return it.get("reward_i_d", 0)
    return 0


@packet_handler(MsgId.GetTreasureAchieveRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetTreasureAchieveRewardReq()
        req.ParseFromString(data)

        rsp = GetTreasureAchieveRewardRsp()

        reward_id = get_achieve_reward_id(req.achieve_id)
        if not reward_id:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GetTreasureAchieveRewardRsp, rsp, packet_id)  # 4527,4528
            return

        # 原子去重(claimed_rewards 表持久化)
        if not db.try_claim(session.player_id, "treasure_achieve", req.achieve_id):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
        else:
            rsp.status = StatusCode.StatusCode_OK

        # 返回全部已领取的成就 id
        rsp.rewarded_achieve_ids.extend(
            sorted(
                int(k) for k in db.get_claimed(session.player_id, "treasure_achieve")
            )
        )

        if rsp.status != StatusCode.StatusCode_OK:
            session.send(MsgId.GetTreasureAchieveRewardRsp, rsp, packet_id)  # 4527,4528
            return

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        # 校验完成进度: 对应奖励池需有挖掘记录(kv ns=archaeology, 由 TreasureDig 写入)
        dig_count = int(
            db.get_kv(session.player_id, "archaeology", str(reward_id), 0) or 0
        )
        if dig_count <= 0:
            rsp.status = StatusCode.StatusCode_FAIL
            db.rollback_claim(session.player_id, "treasure_achieve", req.achieve_id)
            session.send(MsgId.GetTreasureAchieveRewardRsp, rsp, packet_id)  # 4527,4528
            return
        player_level = db.get_players_info(session.player_id, "level")[0]
        items = resolve_reward(reward_id, player_level)
        item_mgr.grant_items(
            session.player_id,
            items,
            rsp_items=rsp.items,
            pack_notice=pack,
            session=session,
        )

        session.send(MsgId.GetTreasureAchieveRewardRsp, rsp, packet_id)  # 4527,4528
        session.send(MsgId.PackNotice, pack, 0)
