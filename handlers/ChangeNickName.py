from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeNickNameReq_pb2
import proto.OverField_pb2 as ChangeNickNameRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeNickNameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeNickNameReq_pb2.ChangeNickNameReq()
        req.ParseFromString(data)

        rsp = ChangeNickNameRsp_pb2.ChangeNickNameRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.nick_name = req.nick_name

        session.player_name = req.nick_name
        db.set_player_name(session.player_id, req.nick_name)

        item = db.get_item_detail(session.player_id, 102)  # 星石-10
        tmp = rsp.items.add()
        tmp.ParseFromString(item)
        tmp.main_item.base_item.num -= 10
        db.up_item_detail(session.player_id, tmp.SerializeToString(), 102, None)

        session.send(
            CmdId.ChangeNickNameRsp, rsp, False, packet_id
        )  # 修改昵称 1527 1528
