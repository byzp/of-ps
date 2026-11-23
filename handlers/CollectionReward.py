from config import Config
from proto.net_pb2 import PackNotice

from utils import achieve_track

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    CollectionRewardReq,
    CollectionRewardRsp,
    StatusCode,
    PBCollectionRewardData,
    RewardStatus,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.reward_resolver import resolve_reward

"""
# 图鉴收集品领奖 1743 1744
奖励链路(已对表验证): CollectionItem.collection_item{i_d, relate_i_d,
new_collection_type} 按类型转到分表取 reward_i_d -> Reward.reward_pool
(如 collection_item 10100001 类型1 -> collection_item_file 10100001
-> reward 101 -> 星石x10)。
类型->分表: 1=collection_item_file 2=collection_item_item 3=collection_item_book
6=collection_item_data 9=collect_item_photo_item;
类型 4(tape)/5(portal)/7(photo_data)/8/10/11 分表无 reward_i_d 字段, 无奖励可发。
领取状态持久化在 collections 表的 PBCollectionRewardData.status:
Collecting 仅对自动到账类型(8/9)收集时置 Reward(官方口径), 可领奖类型
(1/2/3/6...)收集时为 NotReward, 本接口领奖成功后置 Reward;
发奖去重另经 claimed_rewards(system='collection') db.try_claim 原子把关,
防止并发重复领取(blob 的 check-then-set 本身不原子)
"""


@packet_handler(MsgId.CollectionRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectionRewardReq()
        req.ParseFromString(data)

        rsp = CollectionRewardRsp()

        row = db.get_collection(session.player_id, req.item_id)
        if not row:
            rsp.status = StatusCode.StatusCode_NOT_COLLECTED
            session.send(MsgId.CollectionRewardRsp, rsp, packet_id)
            return

        collection_type, item_blob = row
        reward_data = PBCollectionRewardData()
        reward_data.ParseFromString(item_blob)
        reward_data.item_id = req.item_id

        if reward_data.status == RewardStatus.Reward or not db.try_claim(
            session.player_id, "collection", req.item_id
        ):
            rsp.status = StatusCode.StatusCode_COLLECTION_ALREADY_REWARDED
            rsp.collection_reward_data.CopyFrom(reward_data)
            session.send(MsgId.CollectionRewardRsp, rsp, packet_id)
            return

        reward_data.status = RewardStatus.Reward
        db.set_collection(
            session.player_id,
            req.item_id,
            collection_type,
            reward_data.SerializeToString(),
        )

        rsp.status = StatusCode.StatusCode_OK
        rsp.collection_reward_data.CopyFrom(reward_data)
        # collection_item.i_d -> 分表条目的 reward_i_d(无配置/类型无奖励表则 None)
        reward_id = None
        for c in res["CollectionItem"]["collection_item"]["datas"]:
            if c["i_d"] == req.item_id:
                sheet = Config.COLLECTION_REWARD_SHEETS.get(
                    c.get("new_collection_type", 0)
                )
                if sheet:
                    for e in res["CollectionItem"][sheet]["datas"]:
                        if e["i_d"] == c.get("relate_i_d"):
                            reward_id = e.get("reward_i_d")
                            break
                break
        # 类型 4/5/7/8/10/11 或 reward_i_d 缺省(哨兵 999999999)时无奖励, 只标记状态
        lvl_row = db.get_players_info(session.player_id, "level")
        reward_list = resolve_reward(reward_id, lvl_row[0] if lvl_row else 0)

        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                reward_list,
                rsp_items=rsp.items,
                pack_notice=notice,
                session=session,
            )
            session.send(MsgId.CollectionRewardRsp, rsp, packet_id)
            if len(notice.items):
                session.send(MsgId.PackNotice, notice, 0)
