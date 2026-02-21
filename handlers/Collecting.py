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
from utils.pb_create import make_item


@packet_handler(MsgId.CollectingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectingReq()
        req.ParseFromString(data)

        rsp = CollectingRsp()
        rsp.status = StatusCode.StatusCode_OK
        collection = rsp.collections.add()
        item = db.get_collection(session.player_id, req.item_id)
        if item:
            rsp.status = StatusCode.StatusCode_ALREADY_COLLECTED
            session.send(MsgId.CollectingRsp, rsp, packet_id)
            return
        collection.item_map[req.item_id].item_id = req.item_id
        collection.item_map[req.item_id].status = RewardStatus.Reward
        for collection_t in res["CollectionItem"]["collection_item"]["datas"]:
            if collection_t["i_d"] == req.item_id:
                collection.type = collection_t["new_collection_type"]
                break
        db.set_collection(
            session.player_id,
            req.item_id,
            collection.type,
            collection.item_map[req.item_id].SerializeToString(),
        )
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        for item_t in res["Item"]["item"]["datas"]:
            if item_t["i_d"] == req.item_id:
                item_b = db.get_item_detail(session.player_id, item_t["text_i_d"])
                item = rsp1.items.add()
                if item_b:
                    item.ParseFromString(item_b)
                else:
                    item.CopyFrom(make_item(item_t["text_i_d"], 0))
                num_t = item.main_item.base_item.num
                item.main_item.base_item.num = 1
                rsp.items.add().CopyFrom(item)
                item.main_item.base_item.num += num_t
                db.set_item_detail(
                    session.player_id, item.SerializeToString(), item_t["text_i_d"]
                )

        session.send(MsgId.CollectingRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
