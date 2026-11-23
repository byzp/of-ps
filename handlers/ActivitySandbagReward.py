from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivitySandbagRewardReq,
    ActivitySandbagRewardRsp,
    ActivitySandbagRewardType,
    StatusCode,
    PackNotice,
)
import utils.db as db
from handlers.ActivitySandbagHit import interaction_cfg, player_state, lock_sandbag
from utils.reward_resolver import resolve_reward
from utils.res_loader import res

"""
# 打沙袋领奖 4501 4502
- RewardType_Box: seq_list=宝箱序号(ActivitySandbagHit 掉落的内存态宝箱),
  奖励用 resolve_reward 解析宝箱的 reward_pool_group_i_d
  (InteractionActivity.json activity_interaction_item, 指向 Reward.reward_pool)
- RewardType_Server: seq_list=全服进度档位 index, 奖励取
  InteractionActivity.json full_server_activity_item[{index, completion_count,
  full_server_activity_reward_item}]; 私服无全服进度统计, 不校验 completion_count
"""


def _full_server_items(activity_id):
    """full_server_activity 行的档位列表; 活动 id 不匹配时容错取第一条(表内仅一条)"""
    rows = res["InteractionActivity"]["full_server_activity"]["datas"]
    for row in rows:
        if row.get("i_d") == activity_id:
            return row.get("full_server_activity_item", ())
    if rows:
        return rows[0].get("full_server_activity_item", ())
    return ()


@packet_handler(MsgId.ActivitySandbagRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivitySandbagRewardReq()
        req.ParseFromString(data)

        rsp = ActivitySandbagRewardRsp()
        rsp.activity_id = req.activity_id
        rsp.seq_list.extend(req.seq_list)

        row = db.get_players_info(session.player_id, "level")
        player_level = row[0] if row else 0

        rewards = []
        claimed_any = False
        if req.reward_type == ActivitySandbagRewardType.RewardType_Server:
            # 全服进度档位奖励
            items = {
                it.get("index", 0): it for it in _full_server_items(req.activity_id)
            }
            with lock_sandbag:
                st = player_state(session.player_id)
                for seq in req.seq_list:
                    it = items.get(seq)
                    if it is None or seq in st["server_claimed"]:
                        continue
                    st["server_claimed"].add(seq)
                    claimed_any = True
                    for r in it.get("full_server_activity_reward_item", ()):
                        if r.get("item_i_d") and r.get("item_num", 0) > 0:
                            rewards.append((r["item_i_d"], r["item_num"]))
        else:
            # 宝箱奖励(RewardType_Box)
            pool_ids = []
            with lock_sandbag:
                st = player_state(session.player_id)
                for seq in req.seq_list:
                    for box in st["boxes"]:
                        if box["seq"] == seq and not box["used"]:
                            box["used"] = True
                            pool_ids.append(box["pool_id"])
                            break
                    # 宝箱状态已随 sandbag 快照持久化, 重启后未匹配的 seq 直接忽略
            for pool_id in pool_ids:
                claimed_any = True
                rewards.extend(resolve_reward(pool_id, player_level))

        if not claimed_any:
            # 请求的宝箱/档位全部已领过或不存在
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.ActivitySandbagRewardRsp, rsp, packet_id)  # 4501,4502
            return

        rsp.status = StatusCode.StatusCode_OK
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        db.grant_rewards(session.player_id, rewards, rsp.rewards, pack)

        session.send(MsgId.ActivitySandbagRewardRsp, rsp, packet_id)  # 4501,4502
        session.send(MsgId.PackNotice, pack, 0)
