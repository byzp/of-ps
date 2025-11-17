from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as OutfitPresetUpdateReq_pb2
import proto.OverField_pb2 as OutfitPresetUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

# Import ServerSceneSyncDataNotice handler
from handlers.ServerSceneSyncDataNotice import (
    Handler as ServerSceneSyncDataNoticeHandler,
)

logger = logging.getLogger(__name__)


@packet_handler(CmdId.OutfitPresetUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitPresetUpdateReq_pb2.OutfitPresetUpdateReq()
        req.ParseFromString(data)

        rsp = OutfitPresetUpdateRsp_pb2.OutfitPresetUpdateRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.char_id = req.char_id

        # Set preset data - hat, hair, clothes from request, others from hardcoded values
        preset = rsp.preset
        preset.preset_index = TEST_DATA["preset"]["preset_index"]
        preset.hat = req.preset.hat
        preset.hair = req.preset.hair
        preset.clothes = req.preset.clothes
        preset.ornament = TEST_DATA["preset"]["ornament"]
        preset.hat_dye_scheme_index = TEST_DATA["preset"]["hat_dye_scheme_index"]
        preset.hair_dye_scheme_index = TEST_DATA["preset"]["hair_dye_scheme_index"]
        preset.clothes_dye_scheme_index = TEST_DATA["preset"][
            "clothes_dye_scheme_index"
        ]
        preset.ornament_dye_scheme_index = TEST_DATA["preset"][
            "ornament_dye_scheme_index"
        ]

        session.send(CmdId.OutfitPresetUpdateRsp, rsp, False, packet_id)

        # Call ServerSceneSyncDataNotice handler to send scene sync data notification
        try:
            scene_sync_handler = ServerSceneSyncDataNoticeHandler()
            # Create empty data for ServerSceneSyncDataNotice
            scene_sync_handler.handle(session, b"", packet_id)
        except Exception as e:
            logger.error(f"Failed to send ServerSceneSyncDataNotice: {e}")


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "char_id": 401001,
    "preset": {
        "preset_index": 0,
        "hat": 4200331,
        "hair": 4041012,
        "clothes": 4041013,
        "ornament": 0,
        "hat_dye_scheme_index": 0,
        "hair_dye_scheme_index": 0,
        "clothes_dye_scheme_index": 0,
        "ornament_dye_scheme_index": 0,
    },
}
