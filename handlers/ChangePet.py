from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangePetReq, ChangePetRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.ChangePetReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePetReq()
        req.ParseFromString(data)

        rsp = ChangePetRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.pet_instance_id = req.pet_instance_id
        db.set_players_info(session.player_id, "pet_instance_id", req.pet_instance_id)

        session.send(MsgId.ChangePetRsp, rsp, packet_id)
