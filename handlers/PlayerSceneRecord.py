from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as OverField_pb2
import proto.OverField_pb2 as StatusCode_pb2

from utils.bin import bin
from server.scene_data import get_recorder, up_recorder

logger = logging.getLogger(__name__)


@packet_handler(CmdId.PlayerSceneRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OverField_pb2.PlayerSceneRecordReq()
        req.ParseFromString(data)
        up_recorder(
            session.scene_id,
            session.channel_id,
            session.user_id,
            req.data.SerializeToString(),
        )

        rsp = OverField_pb2.PlayerSceneSyncDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK

        for k, v in get_recorder(session.scene_id, session.channel_id).items():
            tmp = rsp.data.add()
            tmp.player_id = k
            tmp.data.add().ParseFromString(v)

        session.send(
            CmdId.PlayerSceneSyncDataNotice, rsp, False, packet_id
        )  # 1203,1206
        #
        # session.sbin(1206, bin["1206-2"], False, packet_id)
