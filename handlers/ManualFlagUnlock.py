from config import Config
from utils.manual_res import iter_flags

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ManualFlagUnlockReq,
    ManualFlagUnlockRsp,
    StatusCode,
    RewardStatus,
)

from utils import achieve_track, flag_state

"""
# 手册旗帜解锁 1863 1864
解锁状态持久化于 kv(ns=manual_flags), ManualList 同步读取。
"""


@packet_handler(MsgId.ManualFlagUnlockReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ManualFlagUnlockReq()
        req.ParseFromString(data)

        rsp = ManualFlagUnlockRsp()

        # 两种旗帜均支持: 手册普通点(manual) 与 秘境发现点(manual_dungeon)

        hit = next(
            ((fid, t, c) for fid, t, c in iter_flags() if fid == req.flag_id),
            None,
        )
        if not hit:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ManualFlagUnlockRsp, rsp, packet_id)
            return

        # 持久化解锁状态(去重)
        added = flag_state.unlock_flags(
            session,
            [req.flag_id],
            namespace=Config.MANUAL_FLAGS_NS,
            notify=False,
        )
        is_new_flag = bool(added)

        rsp.status = StatusCode.StatusCode_OK
        if is_new_flag and hit[1] == "manual":
            # 成就计数: 发现美丽景点(类型11/96, 仅普通手册点;
            # 秘境发现不算景点)
            achieve_track.scenic(session, req.flag_id)

        rsp.flag.flag_id = req.flag_id
        rsp.flag.status = RewardStatus.NotReward  # 刚解锁, 尚未领奖
        session.send(MsgId.ManualFlagUnlockRsp, rsp, packet_id)
