from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as TreasureBoxPickupReq_pb2
import proto.OverField_pb2 as TreasureBoxPickupRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as TreasureBoxData_pb2
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as pb

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.TreasureBoxPickupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureBoxPickupReq_pb2.TreasureBoxPickupReq()
        req.ParseFromString(data)

        rsp = TreasureBoxPickupRsp_pb2.TreasureBoxPickupRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        tb = TreasureBoxData_pb2.TreasureBoxData()
        tb_b = db.get_treasure_box(session.player_id, req.box_index)
        tb.ParseFromString(tb_b)  # 正常不会遇到为空的情况
        rsp1 = PackNotice_pb2.PackNotice()
        rsp1.status = StatusCode_pb2.StatusCode_OK
        if req.pick_index == -1:
            if len(session.temp_pack) >= 30:
                rsp.status = StatusCode_pb2.StatusCode_TEMP_PACK_IS_FULL
                session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
                return
            for item in tb.rewards:
                tmp_i = len(session.temp_pack)
                if tmp_i < 30:  # TODO 动态背包大小限制
                    if item.main_item.item_tag == pb.EBagItemTag_Weapon:
                        instance_id = item.main_item.weapon.instance_id
                    if item.main_item.item_tag == pb.EBagItemTag_Armor:
                        instance_id = item.main_item.armor.instance_id
                    item.pack_type = pb.ItemDetail.PackType.PackType_Inventory
                    db.set_item_detail(
                        session.player_id, item.SerializeToString(), None, instance_id
                    )
                    item.pack_type = pb.ItemDetail.PackType.PackType_TempPack
                    item.main_item.temp_pack_index = tmp_i + 1
                    rsp.items.add().CopyFrom(item)
                    rsp1.items.add().CopyFrom(item)
                    session.temp_pack.append((instance_id, item.SerializeToString()))
                else:
                    session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
                    session.send(MsgId.PackNotice, rsp1, 0)
                    return
            tb.ClearField("rewards")
        else:
            item = tb.rewards[req.pick_index - 1]
            tmp_i = len(session.temp_pack)
            if tmp_i < 30:  # TODO 动态背包大小限制
                if item.main_item.item_tag == pb.EBagItemTag_Weapon:
                    instance_id = item.main_item.weapon.instance_id
                if item.main_item.item_tag == pb.EBagItemTag_Armor:
                    instance_id = item.main_item.armor.instance_id
                item.pack_type = pb.ItemDetail.PackType.PackType_Inventory
                db.set_item_detail(
                    session.player_id, item.SerializeToString(), None, instance_id
                )
                item.pack_type = pb.ItemDetail.PackType.PackType_TempPack
                item.main_item.temp_pack_index = tmp_i + 1
                rsp.items.add().CopyFrom(item)
                rsp1.items.add().CopyFrom(item)
                session.temp_pack.append((instance_id, item.SerializeToString()))
            else:
                rsp.status = StatusCode_pb2.StatusCode_TEMP_PACK_IS_FULL
                session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
                return
            del tb.rewards[req.pick_index - 1]
        db.set_treasure_box(session.player_id, tb.box_id, tb.SerializeToString())

        session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
