from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as SendActionReq_pb2
import proto.OverField_pb2 as SendActionRsp_pb2
import proto.OverField_pb2 as SendActionNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
from server.scene_data import up_action

logger = logging.getLogger(__name__)


@packet_handler(MsgId.SendActionReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SendActionReq_pb2.SendActionReq()
        req.ParseFromString(data)

        tmp = SendActionNotice_pb2.SendActionNotice()
        tmp.status = StatusCode_pb2.StatusCode_OK
        tmp.action_id = req.action_id
        tmp.from_player_id = session.player_id
        tmp.from_player_name = session.player_name
        tmp.is_study = False  # TODO
        up_action(
            session.scene_id,
            session.channel_id,
            tmp,
        )

        rsp = SendActionRsp_pb2.SendActionRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(MsgId.SendActionRsp, rsp, packet_id)  # 1967,1968 ->1970
