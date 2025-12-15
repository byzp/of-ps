from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetAchieveOneGroupRsp_pb2
import proto.OverField_pb2 as GetAchieveOneGroupReq_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetAchieveOneGroupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetAchieveOneGroupReq_pb2.GetAchieveOneGroupReq()
        req.ParseFromString(data)

        rsp = GetAchieveOneGroupRsp_pb2.GetAchieveOneGroupRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(MsgId.GetAchieveOneGroupRsp, rsp) #1761,1762

        i = req.group_id
        if i == 60010000:
            session.sbin(1762, bin["1762-1"], packet_id)
        if i == 60020000:
            session.sbin(1762, bin["1762-2"], packet_id)
        if i == 60030000:
            session.sbin(1762, bin["1762-3"], packet_id)
        if i == 60040000:
            session.sbin(1762, bin["1762-4"], packet_id)
        if i == 60050000:
            session.sbin(1762, bin["1762-5"], packet_id)
        if i == 60060000:
            session.sbin(1762, bin["1762-6"], packet_id)
        if i == 60070000:
            session.sbin(1762, bin["1762-7"], packet_id)
        if i == 60080000:
            session.sbin(1762, bin["1762-8"], packet_id)
        if i == 60090000:
            session.sbin(1762, bin["1762-9"], packet_id)
        if i == 60100000:
            session.sbin(1762, bin["1762-10"], packet_id)
        if i == 60110000:
            session.sbin(1762, bin["1762-11"], packet_id)
