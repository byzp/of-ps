from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import random

from proto.net_pb2 import ItemUseReq, ItemUseRsp, ItemDetail, PackNotice, StatusCode
import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ItemUseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ItemUseReq()
        req.ParseFromString(data)

        rsp = ItemUseRsp()
        rsp.status = StatusCode.StatusCode_OK

        item = db.get_item_detail(session.player_id, req.item_id)
        if not item:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.ItemUseRsp, rsp, packet_id)
            return
        else:
            item_use = ItemDetail()
            item_use.ParseFromString(item)
            if item_use.main_item.base_item.num >= req.num:  # TODO 尚未考虑打折
                item_use.main_item.base_item.num -= req.num
                rsp1 = PackNotice()
                rsp1.status = StatusCode.StatusCode_OK
                rsp1.items.add().CopyFrom(item_use)
                db.set_item_detail(
                    session.player_id, item_use.SerializeToString(), req.item_id, None
                )
            else:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.ItemUseRsp, rsp, packet_id)
                return

        for data in res.get("Reward", {}).get("reward_pool", {}).get("datas", []):
            if data["i_d"] == req.item_id:  # TODO 如果含有武器, 可能引起严重错误
                rp = []
                rsp1.items.add().CopyFrom(item_use)
                for reward_pool in data["reward_pool_group"]:
                    rp.append(reward_pool["reward_pool_group_i_d"])
                for item_pool in (
                    res.get("Reward", {}).get("reward_item_pool", {}).get("datas", [])
                ):
                    if item_pool["i_d"] in rp:
                        for item in item_pool["reward_item_pool_group"]:
                            tmp = db.get_item_detail(
                                session.player_id, item["item_i_d"]
                            )
                            tmp1 = ItemDetail()
                            if not tmp:
                                tmp1.CopyFrom(
                                    make_item(item["item_i_d"], 0, session.player_id)
                                )
                            else:
                                tmp1.ParseFromString(tmp)
                            num_t = tmp1.main_item.base_item.num
                            r_num = random.randint(
                                item["item_min_count"], item["item_max_count"]
                            )
                            tmp1.main_item.base_item.num = r_num
                            rsp.items.add().CopyFrom(tmp1)
                            tmp1.main_item.base_item.num = num_t + r_num
                            rsp1.items.add().CopyFrom(tmp1)
                            db.set_item_detail(
                                session.player_id,
                                tmp1.SerializeToString(),
                                item["item_i_d"],
                                None,
                            )
        session.send(
            MsgId.ItemUseRsp, rsp, packet_id
        )  # 一些测试物品可能没有奖励池,不能放到循环内
        session.send(MsgId.PackNotice, rsp1, 0)
