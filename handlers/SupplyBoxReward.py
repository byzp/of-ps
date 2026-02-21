from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

from proto.net_pb2 import (
    SupplyBoxRewardReq,
    SupplyBoxRewardRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)
import utils.db as db
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.SupplyBoxRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SupplyBoxRewardReq()
        req.ParseFromString(data)

        rsp = SupplyBoxRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        item = db.get_item_detail(
            session.player_id, 101
        )  # TODO 暂时不知道具体奖励内容,先给1000个金币
        tmp1 = ItemDetail()
        if not item:
            tmp1.CopyFrom(
                make_item(
                    101,
                    0,
                    session.player_id,
                )
            )
        else:
            tmp1.ParseFromString(item)
        num_t = tmp1.main_item.base_item.num
        tmp1.main_item.base_item.num = 1000
        rsp.items.add().CopyFrom(tmp1)
        tmp1.main_item.base_item.num = num_t + 1000
        rsp1.items.add().CopyFrom(tmp1)
        db.set_item_detail(
            session.player_id,
            tmp1.SerializeToString(),
            101,
            None,
        )
        rsp.next_reward_time = int(time.time()) + 600

        session.send(MsgId.SupplyBoxRewardRsp, rsp, packet_id)  # 1893 1894
        session.send(MsgId.PackNotice, rsp1, 0)
