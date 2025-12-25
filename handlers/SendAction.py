from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as SendActionReq_pb2
import proto.OverField_pb2 as SendActionRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from server.scene_data import up_action

logger = logging.getLogger(__name__)


@packet_handler(MsgId.SendActionReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SendActionReq_pb2.SendActionReq()
        req.ParseFromString(data)
        up_action(
            session.player_id,
            session.player_name,
            session.scene_id,
            session.channel_id,
            req.action_id,
        )

        rsp = SendActionRsp_pb2.SendActionRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK  # TODO
        session.send(MsgId.SendActionRsp, rsp, packet_id)  # 1967,1968 ->1970
