from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    CollectingReq,
    CollectingRsp,
    PackNotice,
    StatusCode,
    RewardStatus,
)

import utils.db as db
from utils.res_loader import res
from utils import achieve_track
from utils import collection_state, item_mgr

"""
# 图鉴收集 1741 1742(官方抓包 pack0/pack1 实锤)
回包 collections 仅在 OK 时输出一条: {type, item_map{本次条目}, level};
level/exp 按当前场景的 Level 收藏等级表折算，不能直接使用收藏总数。
item_map.status: 仅 type 8/9 收集时即置 Reward(953/16 样本全 Reward),
其余类型(1,2,3,6...)不填状态(NotReward), 由 CollectionReward 领奖链路置位。
ALREADY_COLLECTED / CFG_NOT_FOUND 仅回 status(无 collections)。
"""


@packet_handler(MsgId.CollectingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectingReq()
        req.ParseFromString(data)

        rsp = CollectingRsp()
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        collection_type = 0
        collection_cfg = None
        item_cfg = None
        for entry in res["CollectionItem"]["collection_item"]["datas"]:
            if entry["i_d"] == req.item_id:
                collection_type = entry["new_collection_type"]
                collection_cfg = entry
                break
        if not collection_type:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.CollectingRsp, rsp, packet_id)
            return
        for entry in res["Item"]["item"]["datas"]:
            if entry.get("i_d") == req.item_id:
                item_cfg = entry
                break
        if item_cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.CollectingRsp, rsp, packet_id)
            return
        item_id = item_cfg["text_i_d"]
        rewards = [(item_id, 1)] if item_id else []
        try:
            item_mgr.validate_rewards(rewards)
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.CollectingRsp, rsp, packet_id)
            return

        collection = rsp.collections.add()
        collection.type = collection_type
        collection.item_map[req.item_id].item_id = req.item_id
        if collection_type in Config.COLLECTING_AUTO_REWARD_TYPES:
            collection.item_map[req.item_id].status = RewardStatus.Reward
        try:
            with item_mgr.player_lock(session.player_id), item_mgr.deferred_notifications(), db.transaction():
                if db.get_collection(session.player_id, req.item_id):
                    rsp.status = StatusCode.StatusCode_ALREADY_COLLECTED
                    del rsp.collections[:]
                else:
                    # 持久 claim 是并发最终门禁; 状态与奖励任一失败都整体回滚。
                    if not db.try_claim(
                        session.player_id, "collection_collect", req.item_id
                    ):
                        rsp.status = StatusCode.StatusCode_ALREADY_COLLECTED
                        del rsp.collections[:]
                    else:
                        db.set_collection(
                            session.player_id,
                            req.item_id,
                            collection_type,
                            collection.item_map[req.item_id].SerializeToString(),
                        )
                        if rewards:
                            item_mgr.grant_items(
                                session.player_id,
                                rewards,
                                rsp_items=rsp.items,
                                pack_notice=notice,
                                session=session,
                            )
                        collected = collection_state.scene_items(
                            session.player_id, session.scene_id
                        )
                        collection_state.fill_progress(
                            collection,
                            session.scene_id,
                            len(collected.get(collection_type, ())),
                        )
                        rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.collections[:]
            del rsp.items[:]
            del notice.items[:]

        session.send(MsgId.CollectingRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        with achieve_track.batch(session):
            sub = Config.COLL_TYPE_TO_SUB.get(collection_type)
            if sub:
                achieve_track.collection(session, sub, coll_type=collection_type)
            else:
                achieve_track.explore_collect(session, collection_type)
            achieve_track.report(session, "collect", match=req.item_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
