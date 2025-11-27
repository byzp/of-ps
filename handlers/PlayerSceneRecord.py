from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as PlayerSceneRecordReq_pb2
import proto.OverField_pb2 as PlayerSceneRecordRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

from utils.bin import bin
from server.scene_data import up_recorder

logger = logging.getLogger(__name__)


@packet_handler(CmdId.PlayerSceneRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerSceneRecordReq_pb2.PlayerSceneRecordReq()
        req.ParseFromString(data)

        rec = req.data.SerializeToString()
        up_recorder(
            session.scene_id,
            session.channel_id,
            session.player_id,
            rec,
        )

        # 更新动作和角度
        rec = req.data.char_recorder_data_lst
        if rec:
            rec = rec[0]
            if rec.pos.x != 0:
                session.scene_player.team.char_1.pos.CopyFrom(rec.pos)
                session.scene_player.team.char_1.rot.CopyFrom(rec.rot)
