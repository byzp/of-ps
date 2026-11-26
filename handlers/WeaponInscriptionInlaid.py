from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    WeaponInscriptionInlaidReq,
    WeaponInscriptionInlaidRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

from server import character_growth as growth
from utils import achieve_track
import utils.db as db


def _load_inscription(player_id, inscription_id):
    cfg = growth.item_config(inscription_id)
    if cfg is None or cfg.get("new_bag_item_tag") != 17:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    blob = db.get_item_detail(player_id, inscription_id)
    if not isinstance(blob, (bytes, bytearray)):
        raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
    detail = ItemDetail()
    try:
        detail.ParseFromString(blob)
    except Exception as error:
        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ) from error
    inscription = detail.main_item.inscription
    if (
        detail.main_item.WhichOneof("item") != "inscription"
        or detail.main_item.item_id != inscription_id
        or inscription.inscription_id != inscription_id
        or inscription.level <= 0
    ):
        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
    return detail


def _inscription_cost(inscription_id, level):
    cfg = next(
        (
            row
            for row in growth.rows("Inscription", "inscription")
            if row.get("item_i_d") == inscription_id or row.get("i_d") == inscription_id
        ),
        None,
    )
    groups = cfg.get("inscription_group_info", ()) if cfg else ()
    group = next(
        (row for row in groups if isinstance(row, dict) and row.get("level") == level),
        None,
    )
    if group is None:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    costs = [(101, int(group.get("need_gold_count", 0) or 0))]
    costs.extend(
        (int(entry.get("need_item_i_d", 0) or 0), int(entry.get("item_count", 0) or 0))
        for entry in group.get("inscription_need_item", ()) or ()
    )
    return growth.normalize_costs(cost for cost in costs if cost[0] and cost[1])


@packet_handler(MsgId.WeaponInscriptionInlaidReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WeaponInscriptionInlaidReq()
        req.ParseFromString(data)
        rsp = WeaponInscriptionInlaidRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        cost_notice = PackNotice(status=StatusCode.StatusCode_OK)
        has_cost = False
        try:
            with growth.transaction(session.player_id):
                weapon = growth.load_owned_instance(
                    session.player_id, req.weapon_instance_id, "weapon"
                )
                inscription = _load_inscription(session.player_id, req.inscription_id)
                weapon_state = weapon.main_item.weapon
                inscription_state = inscription.main_item.inscription
                old_id = int(weapon_state.inscription1 or 0)
                previous_host = int(inscription_state.weapon_instance_id or 0)
                if (old_id == req.inscription_id) != (previous_host == req.weapon_instance_id):
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)

                changed_inscriptions = []
                previous_weapon = None
                if old_id and old_id != req.inscription_id:
                    old = _load_inscription(session.player_id, old_id)
                    if old.main_item.inscription.weapon_instance_id != req.weapon_instance_id:
                        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                    old.main_item.inscription.weapon_instance_id = 0
                    changed_inscriptions.append(old)
                if previous_host and previous_host != req.weapon_instance_id:
                    previous_weapon = growth.load_owned_instance(
                        session.player_id, previous_host, "weapon"
                    )
                    if previous_weapon.main_item.weapon.inscription1 != req.inscription_id:
                        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                    previous_weapon.main_item.weapon.inscription1 = 0

                if old_id != req.inscription_id:
                    costs = _inscription_cost(req.inscription_id, inscription_state.level)
                    has_cost = bool(costs)
                    growth.consume(session.player_id, costs, cost_notice)
                    weapon_state.inscription1 = req.inscription_id
                    inscription_state.weapon_instance_id = req.weapon_instance_id

                if previous_weapon is not None:
                    db.set_item_detail(
                        session.player_id,
                        previous_weapon.SerializeToString(),
                        None,
                        previous_host,
                    )
                    rsp.weapon_instances.add().CopyFrom(previous_weapon.main_item.weapon)
                    rsp.items.add().CopyFrom(previous_weapon)
                    notice.items.add().CopyFrom(previous_weapon)
                for changed in changed_inscriptions:
                    changed_id = changed.main_item.item_id
                    db.set_item_detail(
                        session.player_id, changed.SerializeToString(), changed_id
                    )
                    rsp.inscriptions.add().CopyFrom(changed.main_item.inscription)
                    rsp.items.add().CopyFrom(changed)
                    notice.items.add().CopyFrom(changed)
                db.set_item_detail(
                    session.player_id,
                    weapon.SerializeToString(),
                    None,
                    req.weapon_instance_id,
                )
                db.set_item_detail(
                    session.player_id, inscription.SerializeToString(), req.inscription_id
                )
                rsp.weapon_instances.add().CopyFrom(weapon_state)
                rsp.inscriptions.add().CopyFrom(inscription_state)
                rsp.items.add().CopyFrom(weapon)
                rsp.items.add().CopyFrom(inscription)
                notice.items.add().CopyFrom(weapon)
                notice.items.add().CopyFrom(inscription)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.WeaponInscriptionInlaidRsp, rsp, packet_id)
            return

        session.send(MsgId.WeaponInscriptionInlaidRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        if has_cost and cost_notice.items:
            session.send(MsgId.PackNotice, cost_notice, 0)
            costs = _inscription_cost(req.inscription_id, rsp.inscriptions[-1].level)
            coin = sum(count for item_id, count in costs if item_id == 101)
            if coin:
                achieve_track.report(session, "spend_coin", amount=coin)
