from config import Config
from utils.pb_create import make_item

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    OperateMailsReq,
    OperateMailsRsp,
    PackNotice,
    ItemDetail,
    StatusCode,
    MailOperateType,
    MailState,
    EBagItemTag,
    MailBriefData,
)

import utils.db as db
from utils import achieve_track, item_mgr

"""
# 邮件操作 1121 1122(官方抓包 pack0/1772957642-643 实证)
READ: 回包仅 status+operate_type+mails(该封); 无 1400。
CLAIM/CLAIM_ALL: claim_result 逐条回显到账 ItemDetail(货币为本次获得数量),
 mails 回显状态置 CLAIMED 的邮件; 随后一份 1400 + 1720(发放经 item_mgr
 中央归因); 官方回包不填 collect_status(收藏是独立操作)。
非奖励类物品(tag 武器/防具/映像)经 grant_single_item 分配实例落库。
"""


def _detail_tag(detail: ItemDetail) -> int:
    return detail.main_item.item_tag


@packet_handler(MsgId.OperateMailsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OperateMailsReq()
        req.ParseFromString(data)

        rsp = OperateMailsRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.operate_type = req.operate_type
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        match req.operate_type:
            case MailOperateType.MailOperateType_READ:
                mail_b = db.get_mail(session.player_id, req.mail_id)
                if not mail_b:
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                    session.send(MsgId.OperateMailsRsp, rsp, packet_id)
                    return
                mail = rsp.mails.add()
                mail.ParseFromString(mail_b)
                if mail.mail_state == MailState.MailState_CLAIMED:
                    pass  # 阅读已领取邮件不能恢复为可领取状态。
                elif len(mail.reward) or len(mail.items):
                    mail.mail_state = MailState.MailState_UNCLAIM
                else:
                    mail.mail_state = MailState.MailState_READED
                db.set_mail(session.player_id, req.mail_id, mail.SerializeToString())
            case MailOperateType.MailOperateType_DELETE_ALL_READED:
                for mail_b in db.get_mail(session.player_id):
                    mail = MailBriefData()
                    mail.ParseFromString(mail_b)
                    if mail.mail_state == MailState.MailState_CLAIMED or (
                        len(mail.reward) == 0
                        and len(mail.items) == 0
                        and mail.mail_state == MailState.MailState_READED
                    ):
                        rsp.deleted_mail_ids.append(mail.mail_id)
                        db.del_mail(session.player_id, mail.mail_id)
            case (
                MailOperateType.MailOperateType_CLAIM_ALL
                | MailOperateType.MailOperateType_CLAIM
            ):
                with achieve_track.batch(session):
                    for mail_b in db.get_mail(session.player_id):
                        mail = MailBriefData()
                        mail.ParseFromString(mail_b)
                        if mail.mail_state == MailState.MailState_CLAIMED:
                            continue
                        if not (
                            (
                                req.operate_type
                                == MailOperateType.MailOperateType_CLAIM
                                and req.mail_id == mail.mail_id
                            )
                            or req.operate_type
                            == MailOperateType.MailOperateType_CLAIM_ALL
                        ):
                            continue
                        if not (len(mail.items) or len(mail.reward)):
                            continue
                        # items(BaseItem 结构)与 reward(ItemDetail 结构)
                        # 统一发放: 实例类分配 instance_id 落库, 可堆叠类

                        gained = []
                        for bi in mail.items:
                            det = ItemDetail()
                            make_item(bi.item_id, bi.num, session.player_id, det)
                            gained.append((det, bi.num))
                        for it in mail.reward:
                            gained.append((it, it.main_item.base_item.num or 1))
                        for detail, want in gained:
                            item_id = detail.main_item.item_id
                            if item_mgr._is_instance(detail):
                                # 返还掉落的邮件已包含实例与随机属性，必须原样入库。
                                gained_detail = ItemDetail()
                                gained_detail.CopyFrom(detail)
                                gained_detail.pack_type = (
                                    ItemDetail.PackType.PackType_Inventory
                                )
                                item_mgr.mark_new_item(session.player_id, gained_detail)
                                which = gained_detail.main_item.WhichOneof("item")
                                instance_id = getattr(
                                    gained_detail.main_item, which
                                ).instance_id
                                db.set_item_detail(
                                    session.player_id,
                                    gained_detail.SerializeToString(),
                                    None,
                                    instance_id,
                                )
                                rsp1.items.add().CopyFrom(gained_detail)
                            else:
                                gained_detail = item_mgr.grant_single_item(
                                    session.player_id,
                                    item_id,
                                    num=want,
                                    pack_notice=rsp1,
                                )
                            show = rsp.claim_result.add()
                            show.CopyFrom(gained_detail)
                            if show.main_item.WhichOneof("item") == "base_item":
                                show.main_item.base_item.num = want
                            achieve_track.report(
                                session,
                                "gain_item",
                                match=item_id,
                                amount=want,
                            )
                        mail.mail_state = MailState.MailState_CLAIMED
                        rsp.mails.add().CopyFrom(mail)
                        db.set_mail(
                            session.player_id,
                            mail.mail_id,
                            mail.SerializeToString(),
                        )
                    session.send(MsgId.OperateMailsRsp, rsp, packet_id)
                    if rsp1.items:
                        session.send(MsgId.PackNotice, rsp1, 0)
                return

        session.send(MsgId.OperateMailsRsp, rsp, packet_id)  # 1121,1122
        if len(rsp1.items):
            session.send(MsgId.PackNotice, rsp1, 0)
