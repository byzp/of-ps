from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import PlayerLevelRewardReq, PlayerLevelRewardRsp, StatusCode

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.reward_resolver import resolve_reward


@packet_handler(MsgId.PlayerLevelRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerLevelRewardReq()
        req.ParseFromString(data)

        rsp = PlayerLevelRewardRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.level = req.level

        # 已对表确认: Level.player_level 的 reward_i_d 全部为哨兵 999999999
        # (无等级奖励配置), resolve_reward 对哨兵返回空列表, 此处正常不发物品;
        reward_id = 0
        if (
            "Level" in res
            and "player_level" in res["Level"]
            and "datas" in res["Level"]["player_level"]
        ):
            for e in res["Level"]["player_level"]["datas"]:
                if e.get("i_d") == req.level:
                    reward_id = e.get("reward_i_d", 0)
                    break

        rewards = resolve_reward(reward_id, req.level)
        if rewards:
            # 每级奖励只发一次(claimed_rewards 原子去重)
            if not db.try_claim(session.player_id, "player_level", req.level):
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                session.send(
                    MsgId.PlayerLevelRewardRsp, rsp, packet_id
                )  # 玩家等级奖励 1531 1532
                return
            item_mgr.grant_items(
                session.player_id, rewards, rsp_items=rsp.items, session=session
            )

        session.send(
            MsgId.PlayerLevelRewardRsp, rsp, packet_id
        )  # 玩家等级奖励 1531 1532
