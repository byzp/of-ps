from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GachaFullPickReq,
    GachaFullPickRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.pb_create import make_item


@packet_handler(MsgId.GachaFullPickReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaFullPickReq()
        req.ParseFromString(data)

        rsp = GachaFullPickRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        # 满宝箱资格(has_full_pick)由 GachaList 侧展示; 此处仅做发放
        item = rsp.item.add()
        is_character = False
        for c in res.get("Character", {}).get("character", {}).get("datas", []):
            if c.get("i_d") == req.item_id:
                # 已拥有则转换为碎片(repeat_item_i_d)
                item_mgr.grant_character(
                    session.player_id,
                    req.item_id,
                    item,
                    pack_notice=rsp1,
                )
                for i in res.get("Item", {}).get("item", {}).get("datas", []):
                    if i.get("i_d") == item.main_item.item_id:
                        item.extra_quality = i.get("quality", 0)
                        break
                is_character = True
                break

        if not is_character:
            make_item(req.item_id, 1, session.player_id, item)
            if not item.main_item.item_id:
                rsp.status = StatusCode.StatusCode_GACHA_ITEM_NOT_EXIST
                session.send(MsgId.GachaFullPickRsp, rsp, packet_id)
                return
            item_mgr.mark_new_item(session.player_id, item)
            which = item.main_item.WhichOneof("item")
            instance_id = 0
            if which:
                instance_id = getattr(getattr(item.main_item, which), "instance_id", 0)
            if instance_id:
                db.set_item_detail(
                    session.player_id, item.SerializeToString(), None, instance_id
                )
            else:
                # 可堆叠物品按 item_id 合并入背包
                exist_b = db.get_item_detail(session.player_id, req.item_id)
                if exist_b:
                    exist = ItemDetail()
                    exist.ParseFromString(exist_b)
                    item.main_item.base_item.num += exist.main_item.base_item.num
                db.set_item_detail(
                    session.player_id, item.SerializeToString(), req.item_id
                )

        rsp1.items.add().CopyFrom(item)
        db.add_gacha_record(session.player_id, req.gacha_id, req.item_id)

        session.send(MsgId.GachaFullPickRsp, rsp, packet_id)  # 1447,1448
        session.send(MsgId.PackNotice, rsp1, 0)
