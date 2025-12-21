from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

import proto.OverField_pb2 as TreasureBoxOpenReq_pb2
import proto.OverField_pb2 as TreasureBoxOpenRsp_pb2
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

        for item in make_treasure_box_item(
            session.player_id,
            db.get_players_info(session.player_id, "world_level"),
            session.instance_id,
        ):
            item_t = ItemDetail.ItemDetail()
            item_t.ParseFromString(item)
            rsp.items.add().CopyFrom(item_t)
        rsp.next_refresh_time = int(time.time()) + 600

        session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
