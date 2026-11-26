from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    WeaponInscriptionRemoveReq,
    WeaponInscriptionRemoveRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

from server import character_growth as growth
import utils.db as db


@packet_handler(MsgId.WeaponInscriptionRemoveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WeaponInscriptionRemoveReq()
        req.ParseFromString(data)
        rsp = WeaponInscriptionRemoveRsp(
            status=StatusCode.StatusCode_OK, weapon_instance_id=req.weapon_instance_id
        )
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                weapon = growth.load_owned_instance(
                    session.player_id, req.weapon_instance_id, "weapon"
                )
                old_id = int(weapon.main_item.weapon.inscription1 or 0)
                if old_id:
                    inscription_id = old_id
                    cfg = growth.item_config(inscription_id)
                    if cfg is None or cfg.get("new_bag_item_tag") != 17:
                        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
                    blob = db.get_item_detail(session.player_id, inscription_id)
                    if not blob:
                        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                    inscription = ItemDetail()
                    inscription.ParseFromString(blob)
                    if (
                        inscription.main_item.WhichOneof("item") != "inscription"
                        or inscription.main_item.item_id != inscription_id
                        or inscription.main_item.inscription.inscription_id != inscription_id
                        or inscription.main_item.inscription.weapon_instance_id
                        != req.weapon_instance_id
                    ):
                        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                    weapon.main_item.weapon.inscription1 = 0
                    inscription.main_item.inscription.weapon_instance_id = 0
                    db.set_item_detail(
                        session.player_id, weapon.SerializeToString(), None, req.weapon_instance_id
                    )
                    db.set_item_detail(
                        session.player_id, inscription.SerializeToString(), inscription_id
                    )
                    notice.items.add().CopyFrom(weapon)
                    notice.items.add().CopyFrom(inscription)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.WeaponInscriptionRemoveRsp, rsp, packet_id)
            return

        session.send(MsgId.WeaponInscriptionRemoveRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
