from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

import proto.OverField_pb2 as TreasureBoxOpenReq_pb2
import proto.OverField_pb2 as TreasureBoxOpenRsp_pb2
import proto.OverField_pb2 as TreasureBoxData_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as ItemDetail

import utils.db as db
from utils.pb_create import make_treasure_box_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.TreasureBoxOpenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureBoxOpenReq_pb2.TreasureBoxOpenReq()
        req.ParseFromString(data)

        rsp = TreasureBoxOpenRsp_pb2.TreasureBoxOpenRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        tb = TreasureBoxData_pb2.TreasureBoxData()
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
            tb = TreasureBoxData_pb2.TreasureBoxData()
            tb.index = req.treasure_box_index
            tb.box_id = req.treasure_box_index
            for item in make_treasure_box_item(
                session.player_id,
                db.get_players_info(session.player_id, "world_level"),
            ):
                item_t = ItemDetail.ItemDetail()
                item_t.ParseFromString(item)
                tb.rewards.add().CopyFrom(item_t)
                rsp.items.add().CopyFrom(item_t)
            tb.next_refresh_time = time_t + 14400
            rsp.next_refresh_time = time_t + 14400
            db.set_treasure_box(session.player_id, tb.box_id, tb.SerializeToString())

        session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
