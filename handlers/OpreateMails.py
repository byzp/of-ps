from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as OperateMailsReq_pb2
import proto.OverField_pb2 as OperateMailsRsp_pb2
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db
from utils.pb_create import make_item


@packet_handler(MsgId.OperateMailsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OperateMailsReq_pb2.OperateMailsReq()
        req.ParseFromString(data)

        rsp = OperateMailsRsp_pb2.OperateMailsRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.operate_type = req.operate_type
        rsp1 = PackNotice_pb2.PackNotice()
        rsp1.status = StatusCode_pb2.StatusCode_OK
        match req.operate_type:
            case pb.MailOperateType_READ:
                mail_b = db.get_mail(session.player_id, req.mail_id)
                mail = rsp.mails.add()
                mail.ParseFromString(mail_b)
                if len(mail.reward):
                    mail.mail_state = pb.MailState_UNCLAIM
                else:
                    mail.mail_state = pb.MailState_READED
                db.set_mail(session.player_id, req.mail_id, mail.SerializeToString())
            case pb.MailOperateType_DELETE_ALL_READED:
                for mail_b in db.get_mail(session.player_id):
                    mail = pb.MailBriefData()
                    mail.ParseFromString(mail_b)
                    if mail.mail_state == pb.MailState_CLAIMED or (
                        len(mail.reward) == 0
                        and len(mail.items) == 0
                        and mail.mail_state == pb.MailState_READED
                    ):
                        rsp.deleted_mail_ids.append(mail.mail_id)
                        db.del_mail(session.player_id, mail.mail_id)
                        rsp.deleted_mail_ids.append(mail.mail_id)
            case pb.MailOperateType_CLAIM_ALL | pb.MailOperateType_CLAIM:
                for mail_b in db.get_mail(session.player_id):
                    mail = pb.MailBriefData()
                    mail.ParseFromString(mail_b)
                    if (
                        req.operate_type == pb.MailOperateType_CLAIM
                        and req.mail_id == mail.mail_id
                    ) or req.operate_type == pb.MailOperateType_CLAIM_ALL:
                        if len(mail.items):
                            for item in mail.items:
                                item_b = db.get_item_detail(
                                    session.player_id, item.item_id
                                )
                                tmp = rsp1.items.add()
                                if not item_b:
                                    tmp.CopyFrom(
                                        make_item(item.item_id, 0, session.player_id)
                                    )
                                else:
                                    tmp.ParseFromString(item_b)
                                num_t = tmp.main_item.base_item.num
                                tmp.main_item.base_item.num = item.num
                                rsp.claim_result.add().CopyFrom(tmp)
                                tmp.main_item.base_item.num += num_t
                                db.set_item_detail(
                                    session.player_id,
                                    tmp.SerializeToString(),
                                    item.item_id,
                                )
                        if len(mail.reward):
                            for item in mail.reward:
                                if item.main_item.item_tag in [
                                    pb.EBagItemTag_Weapon,
                                    pb.EBagItemTag_Armor,
                                    pb.EBagItemTag_Poster,
                                ]:
                                    if item.main_item.item_tag == pb.EBagItemTag_Weapon:
                                        instance_id = item.main_item.weapon.instance_id
                                    if item.main_item.item_tag == pb.EBagItemTag_Armor:
                                        instance_id = item.main_item.armor.instance_id
                                    if item.main_item.item_tag == pb.EBagItemTag_Poster:
                                        instance_id = item.main_item.poster.instance_id
                                    rsp.claim_result.add().CopyFrom(tmp)
                                    db.set_item_detail(
                                        session.player_id,
                                        item.SerializeToString(),
                                        instance_id=instance_id,
                                    )
                                    rsp1.items.add().CopyFrom(item)
                        mail.mail_state = pb.MailState_CLAIMED
                        rsp.mails.add().CopyFrom(mail)
                        db.set_mail(
                            session.player_id, mail.mail_id, mail.SerializeToString()
                        )

        session.send(MsgId.OperateMailsRsp, rsp, packet_id)  # 1121,1122
        session.send(MsgId.PackNotice, rsp1, 0)
