from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import PetRenameReq, PetRenameRsp, PackNotice, StatusCode

from server import character_growth as growth
import utils.db as db


@packet_handler(MsgId.PetRenameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PetRenameReq()
        req.ParseFromString(data)
        rsp = PetRenameRsp(
            status=StatusCode.StatusCode_OK,
            pet_instance_id=req.pet_instance_id,
            name=req.name,
        )
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                detail = growth.load_owned_instance(
                    session.player_id, req.pet_instance_id, "pet"
                )
                detail.main_item.pet.name = req.name
                db.set_item_detail(
                    session.player_id,
                    detail.SerializeToString(),
                    None,
                    req.pet_instance_id,
                )
                notice.items.add().CopyFrom(detail)
        except growth.GrowthError as error:
            rsp.status = (
                StatusCode.StatusCode_PET_NOT_FOUND
                if error.status == StatusCode.StatusCode_BAD_REQ
                else error.status
            )
            session.send(MsgId.PetRenameRsp, rsp, packet_id)
            return

        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        session.send(MsgId.PetRenameRsp, rsp, packet_id)
