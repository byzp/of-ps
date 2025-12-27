from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as DailyTaskExchangeReq_pb2
import proto.OverField_pb2 as DailyTaskExchangeRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as ItemDetail_pb2
import proto.OverField_pb2 as PackNotice_pb2
import utils.db as db
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DailyTaskExchangeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DailyTaskExchangeReq_pb2.DailyTaskExchangeReq()
        req.ParseFromString(data)

        rsp = DailyTaskExchangeRsp_pb2.DailyTaskExchangeRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        item = db.get_item_detail(session.player_id, 124)  # 祈愿石碎片
        if not item:
            rsp.status = StatusCode_pb2.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
            return
        else:
            item_use = ItemDetail_pb2.ItemDetail()
            item_use.ParseFromString(item)
            if item_use.main_item.base_item.num >= 50:  # TODO 兑换比例
                exc_num = int(item_use.main_item.base_item.num / 50)
                item_use.main_item.base_item.num -= exc_num * 50
                rsp1 = PackNotice_pb2.PackNotice()
                rsp1.status = StatusCode_pb2.StatusCode_OK
                rsp1.items.add().CopyFrom(item_use)
                db.set_item_detail(
                    session.player_id, item_use.SerializeToString(), 124, None
                )
            else:
                rsp.status = StatusCode_pb2.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.ItemUseRsp, rsp, packet_id)
                return

        rsp1.items.add().CopyFrom(item_use)
        tmp = db.get_item_detail(session.player_id, 125)  # 祈愿石
        tmp1 = ItemDetail_pb2.ItemDetail()
        if not tmp:
            tmp1.CopyFrom(make_item(125, 0, session.player_id))
        else:
            tmp1.ParseFromString(tmp)
        num_t = tmp1.main_item.base_item.num
        tmp1.main_item.base_item.num = exc_num
        rsp.rewards.add().CopyFrom(tmp1)
        tmp1.main_item.base_item.num = num_t + exc_num
        rsp1.items.add().CopyFrom(tmp1)
        db.set_item_detail(
            session.player_id,
            tmp1.SerializeToString(),
            125,
            None,
        )
        session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
