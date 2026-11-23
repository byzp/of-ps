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

        collection_type = 0
        for collection_t in res["CollectionItem"]["collection_item"]["datas"]:
            if collection_t["i_d"] == req.item_id:
                collection_type = collection_t["new_collection_type"]
                break
        if not collection_type:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.CollectingRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK

        if db.get_collection(session.player_id, req.item_id):
            rsp.status = StatusCode.StatusCode_ALREADY_COLLECTED
            session.send(MsgId.CollectingRsp, rsp, packet_id)
            return

        collection = rsp.collections.add()
        collection.type = collection_type
        collection.item_map[req.item_id].item_id = req.item_id
        if collection_type in Config.COLLECTING_AUTO_REWARD_TYPES:
            collection.item_map[req.item_id].status = RewardStatus.Reward
        db.set_collection(
            session.player_id,
            req.item_id,
            collection_type,
            collection.item_map[req.item_id].SerializeToString(),
        )
        collected = collection_state.scene_items(session.player_id, session.scene_id)
        collection_state.fill_progress(
            collection, session.scene_id, len(collected.get(collection_type, ()))
        )

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        # 成就计数: 按 collection 子类归因到当前世界(见 utils/achieve_track)
        # 未具名类型(8/9/11)不计成就子类, 但同样推进场景探索度
        with achieve_track.batch(session):
            for item_t in res["Item"]["item"]["datas"]:
                if item_t.get("i_d") == req.item_id:
                    item_mgr.grant_items(
                        session.player_id,
                        [(item_t["text_i_d"], 1)],
                        rsp_items=rsp.items,
                        pack_notice=rsp1,
                        session=session,
                    )
                    break
            sub = Config.COLL_TYPE_TO_SUB.get(collection_type)
            if sub:
                achieve_track.collection(session, sub, coll_type=collection_type)
            else:
                achieve_track.explore_collect(session, collection_type)
            # 成就: 找回[指定收藏品]
            achieve_track.report(session, "collect", match=req.item_id)
            session.send(MsgId.CollectingRsp, rsp, packet_id)
            if len(rsp1.items):
                session.send(MsgId.PackNotice, rsp1, 0)
