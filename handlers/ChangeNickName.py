from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeNickNameReq_pb2
import proto.OverField_pb2 as ChangeNickNameRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb
from server.scene_data import up_scene_action

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeNickNameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeNickNameReq_pb2.ChangeNickNameReq()
        req.ParseFromString(data)

        # 检查是否已存在相同的昵称
        if db.get_player_name_exists(req.nick_name):
            rsp = ChangeNickNameRsp_pb2.ChangeNickNameRsp()
            rsp.status = StatusCode_pb2.StatusCode_DUPLICATED_NAME
            session.send(CmdId.ChangeNickNameRsp, rsp, packet_id)
            return

        rsp = ChangeNickNameRsp_pb2.ChangeNickNameRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.nick_name = req.nick_name

        session.player_name = req.nick_name

        # 存在birthday字段才更新数据库 修复不存在会覆盖为空的问题
        if req.birthday:
            db.set_players_info(session.player_id, "birthday", req.birthday)
        db.set_players_info(session.player_id, "player_name", req.nick_name)

        item = db.get_item_detail(session.player_id, 102)  # 星石-10
        tmp = rsp.items.add()
        tmp.ParseFromString(item)
        tmp.main_item.base_item.num -= 10
        db.set_item_detail(session.player_id, tmp.SerializeToString(), 102, None)

        session.send(CmdId.ChangeNickNameRsp, rsp, packet_id)  # 修改昵称 1527 1528

        # 发送场景同步通知
        notice = pb.ServerSceneSyncDataNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = pb.SceneActionType_UPDATE_NICKNAME

        session.scene_player.player_name = session.player_name
        server_data_entry.player.CopyFrom(session.scene_player)
        up_scene_action(
            session.scene_id, session.channel_id, notice.SerializeToString()
        )
