from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import json
import os

import proto.OverField_pb2 as GachaRecordReq_pb2
import proto.OverField_pb2 as GachaRecordRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GachaRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # Parse request
        req = GachaRecordReq_pb2.GachaRecordReq()
        req.ParseFromString(data)
        
        # Create response message
        rsp = GachaRecordRsp_pb2.GachaRecordRsp()
        
        # Load hardcoded data
        parsed_result = TEST_DATA["parsed_result"]
        
        # Set status
        rsp.status = StatusCode_pb2.StatusCode_OK
        
        # Set fields from parsed result
        rsp.gacha_id = parsed_result.get("gacha_id", 0)
        rsp.page = parsed_result.get("page", 0)
        rsp.total_page = parsed_result.get("total_page", 0)
        
        # Set records
        records_data = parsed_result.get("records", [])
        for record_data in records_data:
            record = rsp.records.add()
            record.gacha_id = record_data.get("gacha_id", 0)
            record.item_id = record_data.get("item_id", 0)
            record.gacha_time = record_data.get("gacha_time", 0)
        
        # Send response
        session.send(CmdId.GachaRecordRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "parsed_result": {
        "status": 1,
        "gacha_id": 0,
        "page": 0,
        "total_page": 88,
        "records": [
            {
                "gacha_id": 3014,
                "item_id": 101001,
                "gacha_time": 1763350670
            },
            {
                "gacha_id": 3013,
                "item_id": 202004,
                "gacha_time": 1761191725
            },
            {
                "gacha_id": 3013,
                "item_id": 11230,
                "gacha_time": 1761191725
            },
            {
                "gacha_id": 3013,
                "item_id": 10210,
                "gacha_time": 1761191725
            },
            {
                "gacha_id": 3013,
                "item_id": 10240,
                "gacha_time": 1761191725
            }
        ]
    }
}