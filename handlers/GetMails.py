from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetMailsRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.GetMailsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetMailsRsp()
        rsp.status = StatusCode.StatusCode_OK

        for mail in db.get_mail(session.player_id):
            rsp.mails.add().ParseFromString(mail)

        session.send(MsgId.GetMailsRsp, rsp, packet_id)  # 1121,1122
