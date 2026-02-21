from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BlessTreeUnlockReq,
    BlessTreeUnlockRsp,
    StatusCode,
    PackNotice,
    ItemDetail,
)

from utils.res_loader import res
from utils.pb_create import make_item

import utils.db as db


@packet_handler(MsgId.BlessTreeUnlockReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BlessTreeUnlockReq()
        req.ParseFromString(data)

        rsp = BlessTreeUnlockRsp()
        rsp.status = StatusCode.StatusCode_OK

        tree_ids = db.get_bless_tree(session.player_id, req.def_id)
        if req.tree_id in tree_ids:
            rsp.status = StatusCode.StatusCode_PLAYER_BLESS_TREE_EXIST
            session.send(MsgId.BlessTreeUnlockRsp, rsp, packet_id)
            return
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        rsp.def_id = req.def_id
        rsp.tree_id = req.tree_id
        for tree in res["BlessingTree"]["blessing_tree_info"]["datas"]:
            if tree["i_d"] == req.def_id:
                for i in tree["blessing_tree_info_group_info"]:
                    if i["box_i_d"] == req.tree_id:
                        item = ItemDetail()
                        item_b = db.get_item_detail(session.player_id, i["item_i_d"])
                        if not item:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            session.send(MsgId.BlessTreeUnlockRsp, rsp, packet_id)
                            return
                        else:
                            item.ParseFromString(item_b)
                            if item.main_item.base_item.num < i["item_count"]:
                                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                                session.send(MsgId.BlessTreeUnlockRsp, rsp, packet_id)
                                return
                            else:
                                item.main_item.base_item.num -= i["item_count"]
                        if (
                            i.get("relate_box_i_d", 0)
                            and not i.get("relate_box_i_d", 0) in tree_ids
                        ):
                            rsp.status = StatusCode.StatusCode_PLAYER_BLESS_NEED_NODE
                            session.send(MsgId.BlessTreeUnlockRsp, rsp, packet_id)
                            return
                        rsp1.items.add().CopyFrom(item)
                        db.set_item_detail(
                            session.player_id, item.SerializeToString(), i["item_i_d"]
                        )
                        item = ItemDetail()
                        item_b = db.get_item_detail(
                            session.player_id, i["reward_item_i_d"]
                        )
                        if item_b:
                            item.ParseFromString(item_b)
                        else:
                            item.CopyFrom(
                                make_item(i["reward_item_i_d"], 0, session.player_id)
                            )
                        num_t = item.main_item.base_item.num
                        item.main_item.base_item.num = i["reward_item_count"]
                        rsp.rewards.add().CopyFrom(item)
                        item.main_item.base_item.num += num_t
                        rsp1.items.add().CopyFrom(item)
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            i["reward_item_i_d"],
                        )

        tree_ids.append(req.tree_id)
        db.set_bless_tree(session.player_id, req.def_id, tree_ids)
        session.send(MsgId.BlessTreeUnlockRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
