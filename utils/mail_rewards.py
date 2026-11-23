"""掉落回收与教学邮件，附件保留生成时的实例号及随机属性。"""

import time

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    ItemDetail,
    MailBriefData,
    MailContentType,
    ReceiveMailNotice,
    PackNotice,
    StatusCode,
)
import utils.db as db
from utils import pb_create


def send_mail(session, rewards, model_id, overdue_day=0):
    if not rewards:
        return
    with db.lock_db:
        row = db.db.execute(
            "SELECT MAX(mail_id) FROM mail WHERE player_id=?", (session.player_id,)
        ).fetchone()
        mail_id = (row[0] or 0) + 1
        mail = MailBriefData(
            mail_id=mail_id,
            model_id=model_id,
            send_time=int(time.time()),
            overdue_day=overdue_day,
            content_type=MailContentType.MailContentType_TEXT_ID,
        )
        for item in rewards:
            mail.reward.add().CopyFrom(item)
        db.set_mail(session.player_id, mail_id, mail.SerializeToString())
    notice = ReceiveMailNotice(status=StatusCode.StatusCode_OK)
    notice.mail.CopyFrom(mail)
    session.send(MsgId.ReceiveMailNotice, notice, 0)


def recover_drops(session):
    with session.drop_lock:
        _recover_drops(session)


def _recover_drops(session):
    rewards = []
    for blobs in session.drop_items.values():
        for blob in blobs:
            item = ItemDetail()
            item.ParseFromString(blob)
            rewards.append(item)
    if rewards:
        send_mail(
            session, rewards, Config.LOST_DROP_MAIL_MODEL, Config.LOST_DROP_MAIL_DAYS
        )
        session.drop_items.clear()


def tutorial_reward(session, talk_id):
    cfg = Config.TUTORIAL_TALK_MAIL_REWARDS.get(talk_id)
    if cfg and db.try_claim(session.player_id, "tutorial_mail", talk_id):
        model_id, rewards = cfg
        items = [
            pb_create.make_item(item_id, count, session.player_id)
            for item_id, count in rewards
        ]
        for item in items:
            item.pack_type = ItemDetail.PackType.PackType_TempStorageArea
        send_mail(session, items, model_id)


def settle_temp_pack(session):
    notice = PackNotice(status=StatusCode.StatusCode_OK, is_clear_temp_pack=True)
    seen = set()
    for instance_id, blob in session.temp_pack:
        item = ItemDetail()
        item.ParseFromString(blob)
        key = (instance_id, item.main_item.item_id)
        if key in seen:
            continue
        seen.add(key)
        raw = (
            db.get_item_detail(session.player_id, None, instance_id)
            if instance_id
            else db.get_item_detail(session.player_id, item.main_item.item_id)
        )
        if raw:
            notice.items.add().ParseFromString(raw)
    session.send(MsgId.PackNotice, notice, 0)
    session.temp_pack.clear()
