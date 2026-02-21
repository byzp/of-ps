from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

from proto.net_pb2 import (
    TreasureBoxOpenReq,
    TreasureBoxOpenRsp,
    TreasureBoxData,
    StatusCode,
)

import utils.db as db
from utils.pb_create import make_treasure_box_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.TreasureBoxOpenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureBoxOpenReq()
        req.ParseFromString(data)

        rsp = TreasureBoxOpenRsp()  # TODO 宝箱种类需要区分
        rsp.status = StatusCode.StatusCode_OK

        tb = TreasureBoxData()
        tb_b = db.get_treasure_box(session.player_id, req.treasure_box_index)
        refresh = False
        time_t = int(time.time())
        if tb_b:
            tb.ParseFromString(tb_b)
            if tb.next_refresh_time < time_t:
                refresh = True
            else:
                for item in tb.rewards:
                    rsp.items.add().CopyFrom(item)
                rsp.next_refresh_time = tb.next_refresh_time
        if not tb_b or refresh:  # TODO 金币直接放背包
            tb = TreasureBoxData()
            tb.index = req.treasure_box_index
            tb.box_id = req.treasure_box_index
            for item in make_treasure_box_item(
                session.player_id,
                db.get_players_info(session.player_id, "world_level"),
            ):
                tb.rewards.add().CopyFrom(item)
                rsp.items.add().CopyFrom(item)
            tb.next_refresh_time = time_t + 14400
            rsp.next_refresh_time = time_t + 14400
            db.set_treasure_box(session.player_id, tb.box_id, tb.SerializeToString())

        session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
