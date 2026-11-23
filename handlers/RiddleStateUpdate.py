from utils import achieve_track as _at

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    RiddleStateUpdateReq,
    RiddleStateUpdateRsp,
    StatusCode,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils.reward_resolver import resolve_reward
from utils import item_mgr

"""
# 谜题状态更新 1323 1324
Riddle.riddle: 100 个场景解谜(翻鼓/铃铛/绣球等, 文案见 string_riddle),
reward_pool_i_d 首通奖励 / repeat_reward_pool_i_d 重复奖励(均为 Reward.reward_pool)。
完成状态持久化于 kv(ns=riddle), 首次通关发首通池, 之后发重复池。
"""


@packet_handler(MsgId.RiddleStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RiddleStateUpdateReq()
        req.ParseFromString(data)

        rsp = RiddleStateUpdateRsp()
        # 解谜动态宝箱(TreasureBox.riddle_treasure_box 按 battle_id 匹配)
        _rows = res["TreasureBox"]["riddle_treasure_box"]["datas"]
        _box = next((b for b in _rows if b.get("i_d") == req.riddle_id), None) or next(
            iter(_rows), None
        )
        if _box:
            rsp.dynamic_treasure_box_base_info.box_id = _box["i_d"]
        rsp.status = StatusCode.StatusCode_BAD_REQ

        # 谜题配置校验
        cfg = next(
            (
                e
                for e in res["Riddle"]["riddle"]["datas"]
                if isinstance(e, dict) and e.get("i_d") == req.riddle_id
            ),
            None,
        )
        if cfg is None:
            session.send(MsgId.RiddleStateUpdateRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        riddle_data = rsp.riddle_data
        riddle_data.riddle_id = req.riddle_id
        riddle_data.state = req.battle_state
        riddle_data.is_win = req.is_win

        # 成就: 空间修复者105(按世界/场景) / 聪明过人118(解谜总数)
        # (在回包前计数, 保证 AchieveNotice 先于 Rsp 到达客户端)
        if req.is_win:

            _at.report(session, "riddle_done")

        session.send(MsgId.RiddleStateUpdateRsp, rsp, packet_id)

        if not req.is_win:
            return

        # 通关奖励: 首通 reward_pool_i_d, 重复 repeat_reward_pool_i_d
        first = not db.get_kv(session.player_id, "riddle", str(req.riddle_id))
        pool_id = (
            cfg.get("reward_pool_i_d") if first else cfg.get("repeat_reward_pool_i_d")
        )
        db.set_kv(session.player_id, "riddle", str(req.riddle_id), 1)
        if not pool_id:
            return

        row = db.get_players_info(session.player_id, "level")
        reward_list = resolve_reward(pool_id, row[0] if row else 0)
        if not reward_list:
            return
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        item_mgr.grant_items(
            session.player_id,
            reward_list,
            pack_notice=pack,
            session=session,
        )
        session.send(MsgId.PackNotice, pack, 0)
