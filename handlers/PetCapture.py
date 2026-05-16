from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config
import random

from proto.net_pb2 import (
    PetCaptureReq,
    PetCaptureRsp,
    PackNotice,
    StatusCode,
    ItemDetail,
)

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item


@packet_handler(MsgId.PetCaptureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PetCaptureReq()
        req.ParseFromString(data)

        rsp = PetCaptureRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        catcher_blob = db.get_item_detail(session.player_id, req.catcher_id)
        if not catcher_blob:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PetCaptureRsp, rsp, packet_id)
            return

        catcher_detail = rsp1.items.add()
        catcher_detail.ParseFromString(catcher_blob)
        if catcher_detail.main_item.base_item.num < 1:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PetCaptureRsp, rsp, packet_id)
            return

        for pet in res["Pet"]["pet"]["datas"]:
            if pet["monster_i_d"] == req.monster_id:
                for item in res["Item"]["item"]["datas"]:
                    if item["i_d"] == req.catcher_id:
                        catcher_quality = item.get("quality", 1)
                        break
                catch_rate = Config.PET_CATCH_RATES[catcher_quality - 1]
                catcher_detail.main_item.base_item.num -= 1
                db.set_item_detail(
                    session.player_id,
                    catcher_detail.SerializeToString(),
                    req.catcher_id,
                )

                if random.uniform(0, 1) <= catch_rate:
                    rsp.success = True
                    pet_item = ItemDetail()
                    make_item(pet["i_d"], 0, session.player_id, pet_item)
                    pet_item.main_item.pet.catch_scene_id = session.scene_id
                    rsp.items.add().CopyFrom(pet_item)
                    rsp1.items.add().CopyFrom(pet_item)
                    db.set_item_detail(
                        session.player_id,
                        pet_item.SerializeToString(),
                        None,
                        pet_item.main_item.pet.instance_id,
                    )

        session.send(MsgId.PackNotice, rsp1, 0)
        session.send(MsgId.PetCaptureRsp, rsp, packet_id)
