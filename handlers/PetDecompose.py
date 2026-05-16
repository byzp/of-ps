from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PetDecomposeReq,
    PetDecomposeRsp,
    PackNotice,
    StatusCode,
    ItemDetail,
)

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item


@packet_handler(MsgId.PetDecomposeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PetDecomposeReq()
        req.ParseFromString(data)

        rsp = PetDecomposeRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        rsp.pet_instance_ids.extend(req.pet_instance_ids)

        reward_items = {}
        for pet_instance_id in req.pet_instance_ids:
            pet_b = db.get_item_detail(session.player_id, None, pet_instance_id)
            if not pet_b:
                continue
            tmp = ItemDetail()
            tmp.ParseFromString(pet_b)
            pet_item_id = tmp.main_item.item_id
            for pet in res["Pet"]["pet"]["datas"]:
                if pet["i_d"] == pet_item_id:
                    for reward_id in pet.get("release_reward", []):
                        if reward_id == 0:
                            continue
                        for reward_group in res["Pet"]["release_reward"]["datas"]:
                            if reward_group["i_d"] == reward_id:
                                for reward_item in reward_group["release_reward_item"]:
                                    item_id = reward_item["release_reward_i_d"]
                                    num = reward_item["release_reward_count"]
                                    reward_items[item_id] = (
                                        reward_items.get(item_id, 0) + num
                                    )
                                break
                    break
            db.del_item_detail(session.player_id, pet_instance_id)

        for item_id, total_num in reward_items.items():
            existing = db.get_item_detail(session.player_id, item_id)
            item_detail = ItemDetail()
            if not existing:
                make_item(item_id, total_num, session.player_id, item_detail)
            else:
                item_detail.ParseFromString(existing)
                item_detail.main_item.base_item.num += total_num
            rsp1.items.add().CopyFrom(item_detail)
            db.set_item_detail(
                session.player_id, item_detail.SerializeToString(), item_id, None
            )

        session.send(MsgId.PackNotice, rsp1, 0)
        session.send(MsgId.PetDecomposeRsp, rsp, packet_id)
