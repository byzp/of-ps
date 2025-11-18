from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import json
import os

import proto.OverField_pb2 as GetWeaponReq_pb2
import proto.OverField_pb2 as GetWeaponRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)

"""
# 获取武器列表 1517 1518
"""


@packet_handler(CmdId.GetWeaponReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetWeaponReq_pb2.GetWeaponReq()
        req.ParseFromString(data)

        rsp = GetWeaponRsp_pb2.GetWeaponRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Load hardcoded data from JSON file
        json_file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "tmp",
            "data",
            "GetWeaponRsp.json",
        )
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)

            parsed_result = json_data.get("parsed_result", {})
            
            # Set status
            rsp.status = parsed_result.get("status", 1)

            # Set weapons
            for weapon_item in parsed_result.get("weapons", []):
                weapon = rsp.weapons.add()
                for key, value in weapon_item.items():
                    if key == "random_property":
                        # Handle repeated random_property field
                        for prop_data in value:
                            prop = weapon.random_property.add()
                            prop.property_type = prop_data["property_type"]
                            prop.value = prop_data["value"]
                    else:
                        setattr(weapon, key, value)

            # Set other fields
            rsp.total_num = parsed_result.get("total_num", 0)
            rsp.end_index = parsed_result.get("end_index", 0)
        except Exception as e:
            logger.error(f"Error loading weapon data from JSON: {e}")
            # Set default values in case of error
            rsp.status = StatusCode_pb2.StatusCode_ERROR

        session.send(CmdId.GetWeaponRsp, rsp, False, packet_id)