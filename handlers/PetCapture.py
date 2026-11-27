from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config
import random

from proto.net_pb2 import PetCaptureReq, PetCaptureRsp, PackNotice, StatusCode, ItemDetail

from server import character_growth as growth
from utils.pb_create import make_item
from utils import achieve_track, item_mgr
import utils.db as db


@packet_handler(MsgId.PetCaptureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PetCaptureReq()
        req.ParseFromString(data)
        rsp = PetCaptureRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        success = False
        try:
            with growth.transaction(session.player_id):
                pet_cfg = next(
                    (
                        row
                        for row in growth.rows("Pet", "pet")
                        if row.get("monster_i_d") == req.monster_id
                    ),
                    None,
                )
                catcher_cfg = growth.item_config(req.catcher_id)
                if pet_cfg is None or catcher_cfg is None:
                    raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
                quality = int(catcher_cfg.get("quality", 1) or 1)
                if (
                    catcher_cfg.get("new_bag_item_tag") != 55
                    or not 1 <= quality <= len(Config.PET_CATCH_RATES)
                    or growth.item_config(pet_cfg.get("i_d", 0)) is None
                ):
                    raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
                if not growth.consume(session.player_id, [(req.catcher_id, 1)], notice):
                    raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                if random.uniform(0, 1) <= Config.PET_CATCH_RATES[quality - 1]:
                    pet_item = ItemDetail()
                    make_item(pet_cfg["i_d"], 0, session.player_id, pet_item)
                    pet_item.main_item.pet.catch_scene_id = session.scene_id
                    # 校验并分配实例 ID；任何后续异常都会回滚捕捉器与实例计数。
                    if (
                        pet_item.main_item.WhichOneof("item") != "pet"
                        or pet_item.main_item.item_id != pet_cfg["i_d"]
                        or pet_item.main_item.pet.item_id != pet_cfg["i_d"]
                        or pet_item.main_item.pet.instance_id <= 0
                    ):
                        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
                    item_mgr.mark_new_item(session.player_id, pet_item)
                    db.set_item_detail(
                        session.player_id,
                        pet_item.SerializeToString(),
                        None,
                        pet_item.main_item.pet.instance_id,
                    )
                    rsp.items.add().CopyFrom(pet_item)
                    notice.items.add().CopyFrom(pet_item)
                    success = True
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.PetCaptureRsp, rsp, packet_id)
            return

        rsp.success = success
        if success:
            achieve_track.report(session, "pet_capture", match=req.monster_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        session.send(MsgId.PetCaptureRsp, rsp, packet_id)
