from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    DailyTaskExchangeReq,
    DailyTaskExchangeRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)
import utils.db as db
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DailyTaskExchangeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DailyTaskExchangeReq()
        req.ParseFromString(data)

        rsp = DailyTaskExchangeRsp()
        rsp.status = StatusCode.StatusCode_OK

        item = db.get_item_detail(session.player_id, 124)  # 祈愿石碎片
        if not item:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
            return
        else:
            item_use = ItemDetail()
            item_use.ParseFromString(item)
            if item_use.main_item.base_item.num >= 50:  # TODO 兑换比例
                exc_num = int(item_use.main_item.base_item.num / 50)
                item_use.main_item.base_item.num -= exc_num * 50
                rsp1 = PackNotice()
                rsp1.status = StatusCode.StatusCode_OK
                rsp1.items.add().CopyFrom(item_use)
                db.set_item_detail(
                    session.player_id, item_use.SerializeToString(), 124, None
                )
            else:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.ItemUseRsp, rsp, packet_id)
                return

        rsp1.items.add().CopyFrom(item_use)
        tmp = db.get_item_detail(session.player_id, 125)  # 祈愿石
        tmp1 = ItemDetail()
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
