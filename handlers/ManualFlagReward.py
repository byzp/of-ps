from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ManualFlagRewardReq,
    ManualFlagRewardRsp,
    StatusCode,
    RewardStatus,
    PackNotice,
)

import utils.db as db
from utils import item_mgr, achieve_track
from utils.manual_res import iter_flags, flag_reward_list

"""
# 手册旗帜领奖 1865 1866
奖励链路解析在 utils/manual_res.py(ManualList 共用):
两种来源都用 un_lock_reward_i_d -> Reward.reward_pool；不发掉落展示素材。
领取状态持久化在 claimed_rewards 表(system='manual_flag'), db.try_claim 原子去重
"""


@packet_handler(MsgId.ManualFlagRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ManualFlagRewardReq()
        req.ParseFromString(data)

        rsp = ManualFlagRewardRsp()

        flag_cfg = None
        sheet = None
        for flag_id, sheet_t, f in iter_flags():
            if flag_id == req.flag_id:
                flag_cfg = f
                sheet = sheet_t
                break
        if flag_cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ManualFlagRewardRsp, rsp, packet_id)
            return

        rsp.flag.flag_id = req.flag_id
        rsp.flag.status = RewardStatus.Reward
        rsp.flag.dungeon_task_finish_num = 0

        # 原子去重(claimed_rewards 表持久化, ManualList 读同一系统)
        if not db.try_claim(session.player_id, "manual_flag", req.flag_id):
            rsp.status = StatusCode.StatusCode_MANUAL_REWARDED
            session.send(MsgId.ManualFlagRewardRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        # 玩家等级供 resolve_reward 按等级过滤奖池
        row = db.get_players_info(session.player_id, "level")
        reward_list = flag_reward_list(sheet, flag_cfg, row[0] if row else 0)
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                reward_list,
                rsp_items=rsp.items,
                pack_notice=pack,
                session=session,
            )
            session.send(MsgId.ManualFlagRewardRsp, rsp, packet_id)
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
