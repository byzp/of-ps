from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import json
import os

import proto.OverField_pb2 as GetPosterReq_pb2
import proto.OverField_pb2 as GetPosterRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)

"""
# 获取映像列表 1405 1406
"""


@packet_handler(CmdId.GetPosterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetPosterReq_pb2.GetPosterReq()
        req.ParseFromString(data)

        rsp = GetPosterRsp_pb2.GetPosterRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # # Load hardcoded data from JSON file
        # json_file_path = os.path.join(
        #     os.path.dirname(__file__),
        #     "..",
        #     "tmp",
        #     "data",
        #     "GetPosterRsp.json",
        # )
        # try:
        #     with open(json_file_path, "r", encoding="utf-8") as f:
        #         json_data = json.load(f)

        #     parsed_result = json_data.get("parsed_result", {})

        #     # Set status
        #     rsp.status = parsed_result.get("status", 1)

        #     # Set posters
        #     for poster_item in parsed_result.get("posters", []):
        #         poster = rsp.posters.add()
        #         for key, value in poster_item.items():
        #             setattr(poster, key, value)

        #     # Set other fields
        #     rsp.total_num = parsed_result.get("total_num", 0)
        #     rsp.end_index = parsed_result.get("end_index", 0)
        # except Exception as e:
        #     logger.error(f"Error loading poster data from JSON: {e}")
        #     # Set default values in case of error
        #     rsp.status = StatusCode_pb2.StatusCode_ERROR

        session.send(CmdId.GetPosterRsp, rsp, False, packet_id)
