"""邮件附件领取：配置预校验、原样发放实例、一次性账本与邮件状态同事务提交。"""

from dataclasses import dataclass, field

from proto.net_pb2 import ItemDetail, MailBriefData, MailState, StatusCode
import utils.db as db
from utils import item_mgr
from server.character_growth import item_config


CLAIM_SYSTEM = "mail_attachment"
_INSTANCE_KINDS = ("weapon", "armor", "poster", "pet", "treasure")
_STACKABLE_EXCLUDED_TAGS = (2, 3, 5, 7, 34, 56)


class MailRewardError(Exception):
    def __init__(self, status):
        super().__init__(StatusCode.Name(status))
        self.status = status


@dataclass
class ClaimResult:
    mails: list = field(default_factory=list)
    gains: list = field(default_factory=list)
    already_claimed: bool = False


def _prepare_rewards(player_id, mail, seen_instances):
    stackables = []
    instances = []
    for base in mail.items:
        item_id = int(base.item_id or 0)
        count = int(base.num or 0)
        cfg = item_config(item_id)
        if (
            count <= 0
            or count > 0x7FFFFFFFFFFFFFFF
            or cfg is None
            or cfg.get("new_bag_item_tag") in _STACKABLE_EXCLUDED_TAGS
        ):
            raise MailRewardError(StatusCode.StatusCode_CFG_NOT_FOUND)
        stackables.append((item_id, count))

    for source in mail.reward:
        detail = ItemDetail()
        detail.CopyFrom(source)
        kind = detail.main_item.WhichOneof("item")
        item_id = int(detail.main_item.item_id or 0)
        cfg = item_config(item_id)
        if not kind or item_id <= 0 or cfg is None:
            raise MailRewardError(StatusCode.StatusCode_CFG_NOT_FOUND)
        if kind not in _INSTANCE_KINDS:
            if kind == "base_item":
                count = int(detail.main_item.base_item.num or 0)
                if count <= 0 or count > 0x7FFFFFFFFFFFFFFF:
                    raise MailRewardError(StatusCode.StatusCode_CFG_NOT_FOUND)
            elif kind == "character":
                count = 1
            else:
                raise MailRewardError(StatusCode.StatusCode_CFG_NOT_FOUND)
            if kind != "character" and cfg.get("new_bag_item_tag") in _STACKABLE_EXCLUDED_TAGS:
                raise MailRewardError(StatusCode.StatusCode_CFG_NOT_FOUND)
            stackables.append((item_id, count))
            continue

        instance = getattr(detail.main_item, kind)
        instance_id = int(getattr(instance, "instance_id", 0) or 0)
        if (
            instance_id <= 0
            or instance_id in seen_instances
            or getattr(instance, f"{kind}_id", getattr(instance, "item_id", 0)) != item_id
            or db.get_item_detail(player_id, None, instance_id)
        ):
            raise MailRewardError(StatusCode.StatusCode_BAD_REQ)
        seen_instances.add(instance_id)
        detail.pack_type = ItemDetail.PackType.PackType_Inventory
        detail.main_item.is_new = False
        detail.main_item.temp_pack_index = 0
        if hasattr(instance, "wearer_id"):
            instance.wearer_id = 0
        instances.append(detail)
    return stackables, instances


def _grant_prepared(player_id, prepared, claim_result, pack_notice):
    for stackables, instances in prepared:
        if stackables:
            item_mgr.grant_items(
                player_id,
                stackables,
                rsp_items=claim_result,
                pack_notice=pack_notice,
                session=None,
            )
        for detail in instances:
            item_mgr.mark_new_item(player_id, detail)
            kind = detail.main_item.WhichOneof("item")
            instance_id = getattr(detail.main_item, kind).instance_id
            db.set_item_detail(player_id, detail.SerializeToString(), None, instance_id)
            claim_result.add().CopyFrom(detail)
            pack_notice.items.add().CopyFrom(detail)


def _claimed_mail(player_id, mail):
    # 老版本可能已经发放但仍保留附件；只清理展示状态，绝不再次发放。
    db.try_claim(player_id, CLAIM_SYSTEM, str(mail.mail_id))
    mail.mail_state = MailState.MailState_CLAIMED
    mail.ClearField("items")
    mail.ClearField("reward")
    db.set_mail(player_id, mail.mail_id, mail.SerializeToString())


def claim_attachments(player_id, mail_id=0, claim_all=False, claim_result=None, pack_notice=None):
    """领取单封或全部附件。返回已领取邮件和本次到账明细。

    单封重复领取通过 already_claimed 返回；CLAIM_ALL 重复调用是成功的空操作。
    整个请求要么全部到账并清除附件，要么零变更。
    """
    if claim_result is None or pack_notice is None:
        raise ValueError("claim_result and pack_notice are required")
    if not claim_all and not mail_id:
        raise MailRewardError(StatusCode.StatusCode_BAD_REQ)
    result = ClaimResult()
    with item_mgr.player_lock(player_id), db.transaction():
        blobs = db.get_mail(player_id)
        selected = []
        for blob in blobs:
            mail = MailBriefData()
            try:
                mail.ParseFromString(blob)
            except Exception as error:
                raise MailRewardError(StatusCode.StatusCode_BAD_REQ) from error
            if not mail.mail_id:
                raise MailRewardError(StatusCode.StatusCode_BAD_REQ)
            if claim_all or mail.mail_id == mail_id:
                selected.append(mail)
        if not claim_all and not selected:
            raise MailRewardError(StatusCode.StatusCode_BAD_REQ)

        prepared = []
        seen_instances = set()
        for mail in selected:
            already_claimed = mail.mail_state == MailState.MailState_CLAIMED or db.has_claimed(
                player_id, CLAIM_SYSTEM, str(mail.mail_id)
            )
            if already_claimed:
                _claimed_mail(player_id, mail)
                result.mails.append(mail)
                result.already_claimed = True
                continue
            if not (len(mail.items) or len(mail.reward)):
                continue
            prepared.append((mail, _prepare_rewards(player_id, mail, seen_instances)))
            if not prepared[-1][1][0] and not prepared[-1][1][1]:
                raise MailRewardError(StatusCode.StatusCode_CFG_NOT_FOUND)

        # 所有邮件均通过校验后才写领取账本和物品；后续异常由事务整体回滚。
        for mail, rewards in prepared:
            if not db.try_claim(player_id, CLAIM_SYSTEM, str(mail.mail_id)):
                _claimed_mail(player_id, mail)
                result.mails.append(mail)
                result.already_claimed = True
                continue
            before = len(claim_result)
            _grant_prepared(player_id, [rewards], claim_result, pack_notice)
            for gained in claim_result[before:]:
                item_id = int(gained.main_item.item_id or 0)
                kind = gained.main_item.WhichOneof("item")
                count = (
                    int(gained.main_item.base_item.num or 0)
                    if kind == "base_item"
                    else 1
                )
                if count > 0:
                    result.gains.append((item_id, count))
            mail.mail_state = MailState.MailState_CLAIMED
            mail.ClearField("items")
            mail.ClearField("reward")
            db.set_mail(player_id, mail.mail_id, mail.SerializeToString())
            result.mails.append(mail)

        if not claim_all and not result.mails:
            raise MailRewardError(StatusCode.StatusCode_MAIL_NO_REWARD)
    return result


def sanitize_claimed_mails(player_id):
    """列表/重启读取时清理历史已领取邮件残留附件，并补一次性账本。"""
    changed = False
    with item_mgr.player_lock(player_id), db.transaction():
        for blob in db.get_mail(player_id):
            mail = MailBriefData()
            try:
                mail.ParseFromString(blob)
            except Exception:
                continue
            if mail.mail_state != MailState.MailState_CLAIMED:
                continue
            before = mail.SerializeToString()
            _claimed_mail(player_id, mail)
            changed = changed or mail.SerializeToString() != before
    return changed
