from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GatherReq_pb2
import proto.OverField_pb2 as GatherRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as ItemDetail_pb2
import proto.OverField_pb2 as PackNotice_pb2
import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GatherReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GatherReq_pb2.GatherReq()
        req.ParseFromString(data)

        rsp = GatherRsp_pb2.GatherRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.index = req.gather_item.index
        rsp.item_level = 1

        rsp1 = PackNotice_pb2.PackNotice()
        rsp1.status = StatusCode_pb2.StatusCode_OK
        for data in res.get("Gather", {}).get("gather", {}).get("datas", []):
            for info in data["gather_group_info"]:
                if info["reward"] == req.gather_item.reward:
                    rsp.group_gather_limit.gather_group_id = data["i_d"]
                    gather_limit = rsp.group_gather_limit.gather_limit
                    gather_limit.gather_type = info["new_weapon_type"]  # ?
                    gather_limit.gather_num = 5  # TODO 采集数量限制
                    gather_limit.gather_limit_num = 1
                    rsp.scene_gather_limit.scene_id = session.scene_id
                    gather_limit_s = rsp.scene_gather_limit.gather_limits.add()
                    gather_limit_s.CopyFrom(gather_limit)
                    for gather_reward in (
                        res.get("Gather", {}).get("gather_reward", {}).get("datas", [])
                    ):
                        if gather_reward["i_d"] == info["reward"]:
                            if req.gather_item.is_lucky:
                                item_t = gather_reward["gather_reward_group_info"][1]
                            else:
                                item_t = gather_reward["gather_reward_group_info"][0]
                            item = db.get_item_detail(
                                session.player_id, item_t["item_i_d"]
                            )
                            tmp1 = ItemDetail_pb2.ItemDetail()
                            if not item:
                                tmp1.CopyFrom(
                                    make_item(
                                        item_t["item_i_d"],
                                        0,
                                        session.player_id,
                                    )
                                )
                            else:
                                tmp1.ParseFromString(item)
                            num_t = tmp1.main_item.base_item.num
                            tmp1.main_item.base_item.num = item_t["count"]
                            rsp.items.add().CopyFrom(tmp1)
                            tmp1.main_item.base_item.num = num_t + item_t["count"]
                            rsp1.items.add().CopyFrom(tmp1)
                            db.set_item_detail(
                                session.player_id,
                                tmp1.SerializeToString(),
                                item_t["item_i_d"],
                                None,
                            )
                            session.send(
                                MsgId.GatherRsp, rsp, packet_id
                            )  # TODO 任务进度通知
                            session.send(MsgId.PackNotice, rsp1, 0)
                            return
