from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import json
import os

import proto.OverField_pb2 as GachaRecordReq_pb2
import proto.OverField_pb2 as GachaRecordRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GachaRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # Parse request
        req = GachaRecordReq_pb2.GachaRecordReq()
        req.ParseFromString(data)

        # Create response message
        rsp = GachaRecordRsp_pb2.GachaRecordRsp()

        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.gacha_id = req.gacha_id
        rsp.page = req.page

        records = db.get_gacha_records(
            session.player_id,
            req.gacha_id,
            req.page,
        )

        rsp.total_page = db.get_gacha_record_total_page(
            session.player_id,
            req.gacha_id,
        )

        for item_id, gacha_time in records:
            rec = rsp.records.add()
            rec.gacha_id = req.gacha_id
            rec.item_id = item_id
            rec.gacha_time = gacha_time

        session.send(MsgId.GachaRecordRsp, rsp, packet_id)

