from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ManualListRsp, StatusCode, RewardStatus

from utils.manual_res import iter_flags
import utils.db as db
from config import Config
from utils import flag_state

"""
# 手册旗帜列表 1861 1862
旗帜来源 utils/manual_res.iter_flags(与 ManualFlagReward 相同遍历):
仅下发玩家实际发现的地标，领取状态从manual_flag记录恢复。
注: dungeon_task_finish_num 官方在领奖后回 1(副本任务完成数),
Manual 表中旗帜与副本任务无映射字段, 服务端无从统计, 回 0 客户端仅作展示
"""


@packet_handler(MsgId.ManualListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = ManualListRsp()
        rsp.status = StatusCode.StatusCode_OK

        unlocked = flag_state.get_ids(session.player_id, Config.MANUAL_FLAGS_NS)
        claimed = {int(key) for key in db.get_claimed(session.player_id, "manual_flag")}
        for flag_id in sorted(unlocked):
            tmp = rsp.flags.add()
            tmp.flag_id = flag_id
            tmp.status = (
                RewardStatus.Reward if flag_id in claimed else RewardStatus.NotReward
            )
            tmp.dungeon_task_finish_num = 0

        session.send(MsgId.ManualListRsp, rsp, packet_id)  # 1861,1862
