from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import json
import os

import proto.OverField_pb2 as GetArmorReq_pb2
import proto.OverField_pb2 as GetArmorRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)

"""
# 获取防具列表 1403 1404
"""


@packet_handler(CmdId.GetArmorReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetArmorReq_pb2.GetArmorReq()
        req.ParseFromString(data)

        rsp = GetArmorRsp_pb2.GetArmorRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Load hardcoded data from JSON file
        json_file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "tmp",
            "data",
            "GetArmorRsp.json",
        )
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)

            parsed_result = json_data.get("parsed_result", {})
            
            # Set status
            rsp.status = parsed_result.get("status", 1)

            # Set armors
            for armor_item in parsed_result.get("armors", []):
                armor = rsp.armors.add()
                for key, value in armor_item.items():
                    if key == "random_property":
                        # Handle repeated random_property field
                        for prop_data in value:
                            prop = armor.random_property.add()
                            prop.property_type = prop_data["property_type"]
                            prop.value = prop_data["value"]
                    else:
                        setattr(armor, key, value)

            # Set other fields
            rsp.total_num = parsed_result.get("total_num", 0)
            rsp.end_index = parsed_result.get("end_index", 0)
        except Exception as e:
            logger.error(f"Error loading armor data from JSON: {e}")
            # Set default values in case of error
            rsp.status = StatusCode_pb2.StatusCode_ERROR

        session.send(CmdId.GetArmorRsp, rsp, False, packet_id)