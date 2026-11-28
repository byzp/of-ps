from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import WeaponStrengthReq, WeaponStrengthRsp, StatusCode, PackNotice

from server import character_growth as growth
from utils import achieve_track
import utils.db as db


@packet_handler(MsgId.WeaponStrengthReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WeaponStrengthReq()
        req.ParseFromString(data)
        rsp = WeaponStrengthRsp(status=StatusCode.StatusCode_OK, weapon_instance_id=req.weapon_instance_id)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                detail = growth.load_owned_instance(session.player_id, req.weapon_instance_id, "weapon")
                weapon = detail.main_item.weapon
                target, costs = growth.strengthen_entry("weapon", weapon)
                growth.consume(session.player_id, costs, notice)
                weapon.strength_level = target
                weapon.strength_exp = 0
                db.set_item_detail(
                    session.player_id, detail.SerializeToString(), None, req.weapon_instance_id
                )
                rsp.strength_level = target
                notice.items.add().CopyFrom(detail)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
            return

        session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        achieve_track.report(session, "weapon_enhance")
