from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    OperateMailsReq,
    OperateMailsRsp,
    PackNotice,
    StatusCode,
    MailOperateType,
    MailState,
    MailBriefData,
)

from server import character_growth as growth
from server import mail_rewards
from utils import achieve_track
import utils.db as db


def _parse(blob):
    mail = MailBriefData()
    try:
        mail.ParseFromString(blob)
    except Exception as error:
        raise mail_rewards.MailRewardError(StatusCode.StatusCode_BAD_REQ) from error
    if not mail.mail_id:
        raise mail_rewards.MailRewardError(StatusCode.StatusCode_BAD_REQ)
    return mail


@packet_handler(MsgId.OperateMailsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OperateMailsReq()
        req.ParseFromString(data)
        rsp = OperateMailsRsp(status=StatusCode.StatusCode_OK, operate_type=req.operate_type)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        gains = []
        try:
            match req.operate_type:
                case MailOperateType.MailOperateType_READ:
                    mail_rewards.sanitize_claimed_mails(session.player_id)
                    with growth.transaction(session.player_id):
                        blob = db.get_mail(session.player_id, req.mail_id)
                        if not blob:
                            raise mail_rewards.MailRewardError(
                                StatusCode.StatusCode_MAIL_NOT_EXIST
                            )
                        mail = _parse(blob)
                        if mail.mail_state == MailState.MailState_CLAIMED or db.has_claimed(
                            session.player_id,
                            mail_rewards.CLAIM_SYSTEM,
                            str(mail.mail_id),
                        ):
                            db.try_claim(
                                session.player_id,
                                mail_rewards.CLAIM_SYSTEM,
                                str(mail.mail_id),
                            )
                            mail.mail_state = MailState.MailState_CLAIMED
                            mail.ClearField("items")
                            mail.ClearField("reward")
                        elif len(mail.reward) or len(mail.items):
                            mail.mail_state = MailState.MailState_UNCLAIM
                        else:
                            mail.mail_state = MailState.MailState_READED
                        db.set_mail(session.player_id, mail.mail_id, mail.SerializeToString())
                        rsp.mails.add().CopyFrom(mail)
                case MailOperateType.MailOperateType_DELETE_ALL_READED:
                    with growth.transaction(session.player_id):
                        for blob in db.get_mail(session.player_id):
                            mail = _parse(blob)
                            if mail.mail_state == MailState.MailState_CLAIMED or (
                                not len(mail.reward)
                                and not len(mail.items)
                                and mail.mail_state == MailState.MailState_READED
                            ):
                                rsp.deleted_mail_ids.append(mail.mail_id)
                                db.del_mail(session.player_id, mail.mail_id)
                case (
                    MailOperateType.MailOperateType_CLAIM_ALL
                    | MailOperateType.MailOperateType_CLAIM
                ):
                    result = mail_rewards.claim_attachments(
                        session.player_id,
                        mail_id=req.mail_id,
                        claim_all=req.operate_type == MailOperateType.MailOperateType_CLAIM_ALL,
                        claim_result=rsp.claim_result,
                        pack_notice=notice,
                    )
                    rsp.mails.extend(result.mails)
                    gains = result.gains
                    if (
                        req.operate_type == MailOperateType.MailOperateType_CLAIM
                        and result.already_claimed
                    ):
                        rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                        rsp.ClearField("mails")
                        rsp.ClearField("claim_result")
                case _:
                    raise mail_rewards.MailRewardError(StatusCode.StatusCode_BAD_REQ)
        except mail_rewards.MailRewardError as error:
            rsp.status = error.status
            session.send(MsgId.OperateMailsRsp, rsp, packet_id)
            return

        session.send(MsgId.OperateMailsRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        if gains:
            with achieve_track.batch(session):
                for item_id, count in gains:
                    achieve_track.report(
                        session, "gain_item", match=item_id, amount=count
                    )
