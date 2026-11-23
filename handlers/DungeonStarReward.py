from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    DungeonStarRewardReq,
    DungeonStarRewardRsp,
    StatusCode,
    DungeonData,
    RewardStatus,
    PackNotice,
)

import utils.db as db
from utils import item_mgr


@packet_handler(MsgId.DungeonStarRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonStarRewardReq()
        req.ParseFromString(data)

        rsp = DungeonStarRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        # dungeon_id=0 时 db.get_dungeon 会返回 dict 而非 bytes, 先拒绝
        if not req.dungeon_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.DungeonStarRewardRsp, rsp, packet_id)  # 1345,1346
            return

        # 领取副本星级奖励, 用 DungeonData.star_reward 去重
        dg = DungeonData()
        blob = db.get_dungeon(session.player_id, req.dungeon_id)
        if blob:
            dg.ParseFromString(blob)
        dg.dungeon_id = req.dungeon_id

        if dg.star_reward == RewardStatus.Reward:
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.DungeonStarRewardRsp, rsp, packet_id)
            return

        dg.star_reward = RewardStatus.Reward
        db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())

        # 星级奖励配置未找到, 保留金币占位。已查表:
        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        item_mgr.grant_items(
            session.player_id,
            [(101, 100)],
            rsp_items=rsp.rewards,
            pack_notice=notice,
            session=session,
        )

        session.send(MsgId.DungeonStarRewardRsp, rsp, packet_id)  # 1345,1346
        session.send(MsgId.PackNotice, notice, 0)  # 1400
