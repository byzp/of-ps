from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import AreaUnlockReq, AreaUnlockRsp, StatusCode, AreaData

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.AreaUnlockReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaUnlockReq()
        req.ParseFromString(data)

        rsp = AreaUnlockRsp()
        rsp.status = StatusCode.StatusCode_OK
        area_b = db.get_area(session.player_id, session.scene_id, req.area_id)
        if area_b:
            rsp.status = StatusCode.StatusCode_AREA_ALREADY_UNLOCK
        else:
            rsp.area.area_id = req.area_id
            rsp.area.area_state = AreaData.AreaState.Unlock
            rsp.area.level = 1
            db.set_area(
                session.player_id,
                session.scene_id,
                req.area_id,
                rsp.area.SerializeToString(),
            )

        session.send(MsgId.AreaUnlockRsp, rsp, packet_id)
