from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

import proto.OverField_pb2 as SupplyBoxRewardReq_pb2
import proto.OverField_pb2 as SupplyBoxRewardRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as ItemDetail
import proto.OverField_pb2 as PackNotice_pb2
import utils.db as db
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.SupplyBoxRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SupplyBoxRewardReq_pb2.SupplyBoxRewardReq()
        req.ParseFromString(data)

        rsp = SupplyBoxRewardRsp_pb2.SupplyBoxRewardRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp1 = PackNotice_pb2.PackNotice()
        rsp1.status = StatusCode_pb2.StatusCode_OK
        item = db.get_item_detail(
            session.player_id, 101
        )  # TODO 暂时不知道具体奖励内容,先给1000个金币
        tmp1 = ItemDetail.ItemDetail()
        if not item:
            item = make_item(
                101,
                0,
                session.player_id,
            )
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
