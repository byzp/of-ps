from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetAchieveOneGroupRsp_pb2
import proto.OverField_pb2 as GetAchieveOneGroupReq_pb2
import proto.OverField_pb2 as OneGroupAchieveInfo_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetAchieveOneGroupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetAchieveOneGroupReq_pb2.GetAchieveOneGroupReq()
        req.ParseFromString(data)

        rsp = GetAchieveOneGroupRsp_pb2.GetAchieveOneGroupRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        achieve = db.get_achieve(session.player_id, req.group_id)
        tmp = OneGroupAchieveInfo_pb2.OneGroupAchieveInfo()
        tmp.ParseFromString(achieve)
        rsp.current_group_achieve_info.CopyFrom(tmp)

        session.send(MsgId.GetAchieveOneGroupRsp, rsp, packet_id)  # 1761,1762, 成就
