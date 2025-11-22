from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetArchiveInfoRsp_pb2
import proto.OverField_pb2 as Scene_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

from utils.bin import bin
from server.scene_data import up_scene_action, get_and_up_players
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeMusicalItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetArchiveInfoRsp_pb2.GetArchiveInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(CmdId.ChangeMusicalItemRsp, rsp, False, packet_id)  # 2671,2672

        notice = Scene_pb2.ServerSceneSyncDataNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = pb.SceneActionType_UPDATE_MUSICAL_ITEM
        up_scene_action(
            session.scene_id, session.channel_id, notice.SerializeToString()
        )

        # 视为完成登录，同步场景玩家并广播加入事件
        if session.logged_in == False:
            session.logged_in = True
            for i in get_and_up_players(
                session.scene_id, session.channel_id, session.player_id
            ):
                rsp = pb.ServerSceneSyncDataNotice()
                rsp.ParseFromString(i)
                session.send(CmdId.ServerSceneSyncDataNotice, rsp, False, 0)
            num = 0

            rsp = pb.PackNotice()
            rsp.status = StatusCode_pb2.StatusCode_OK
            rsp.temp_pack_max_size = 30
            for item in db.get_item_detail(session.player_id):
                rsp.items.add().ParseFromString(item)
                num += 1
                if num > 10000:
                    session.send(CmdId.PackNotice, rsp, True, packet_id)
                    rsp = pb.PackNotice()
                    rsp.status = StatusCode_pb2.StatusCode_OK
                    rsp.temp_pack_max_size = 30
                    num = 0
