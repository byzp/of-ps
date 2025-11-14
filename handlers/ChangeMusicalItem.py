from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetArchiveInfoRsp_pb2
import proto.OverField_pb2 as Scene_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeMusicalItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetArchiveInfoRsp_pb2.GetArchiveInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(CmdId.ChangeMusicalItemRsp, rsp, False, packet_id)  # 2671,2672
        # session.sbin(2672, "tmp\\bin\\packet_103_2672_servertoclient_body.bin")

        notice = Scene_pb2.ServerSceneSyncDataNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.user_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = 23
        server_data_entry.player.CopyFrom(Scene_pb2.SceneServerData().player)
        # session.send(CmdId.ServerSceneSyncDataNotice, notice)
        session.sbin(1208, bin["1208"], False, packet_id)  # TODO
