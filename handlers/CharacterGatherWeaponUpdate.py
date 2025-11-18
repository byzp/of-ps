from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CharacterGatherWeaponUpdateReq_pb2
import proto.OverField_pb2 as CharacterGatherWeaponUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.CharacterGatherWeaponUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterGatherWeaponUpdateReq_pb2.CharacterGatherWeaponUpdateReq()
        req.ParseFromString(data)
        # TODO

        rsp = CharacterGatherWeaponUpdateRsp_pb2.CharacterGatherWeaponUpdateRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(
            CmdId.CharacterGatherWeaponUpdateRsp, rsp, False, packet_id
        )  # 1955,1956
