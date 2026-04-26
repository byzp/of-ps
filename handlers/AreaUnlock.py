from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import AreaUnlockReq, AreaUnlockRsp, StatusCode, AreaData

import utils.db as db
from utils.pb_create import make_QuestNotice


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
        if not Config.SKIP_QUESTS and req.area_id == 1001:
            rsp1 = make_QuestNotice(session.player_id, [11000231])
            if rsp1:
                session.send(MsgId.QuestNotice, rsp1, 0)

        session.send(MsgId.AreaUnlockRsp, rsp, packet_id)
