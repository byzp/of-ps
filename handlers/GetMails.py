from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import GetMailsRsp, StatusCode, MailBriefData

from server import mail_rewards
import utils.db as db


@packet_handler(MsgId.GetMailsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetMailsRsp(status=StatusCode.StatusCode_OK)
        mail_rewards.sanitize_claimed_mails(session.player_id)
        for blob in db.get_mail(session.player_id):
            mail = MailBriefData()
            try:
                mail.ParseFromString(blob)
            except Exception:
                rsp.status = StatusCode.StatusCode_SYS_ERR
                session.send(MsgId.GetMailsRsp, rsp, packet_id)
                return
            rsp.mails.add().CopyFrom(mail)
        session.send(MsgId.GetMailsRsp, rsp, packet_id)
