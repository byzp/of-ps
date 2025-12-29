from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random

import proto.OverField_pb2 as MonsterDeadReq_pb2
import proto.OverField_pb2 as MonsterDeadRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

from utils.res_loader import res
from utils.pb_create import make_item


@packet_handler(MsgId.MonsterDeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MonsterDeadReq_pb2.MonsterDeadReq()
        req.ParseFromString(data)

        rsp = MonsterDeadRsp_pb2.MonsterDeadRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.monster_index = req.monster_index  # TODO ?
        if not bool(random.randint(0, 1)) or True:
            if len(session.drop_items) == 0:
                rsp.drop_item.index = 1
            else:
                rsp.drop_item.index = list(session.drop_items.keys())[-1] + 1
            if bool(random.randint(0, 1)):
                armor_len = len(res["Armor"]["armor"]["datas"])
                item_i = res["Armor"]["armor"]["datas"][
                    random.randint(0, armor_len - 1)
                ]
                item = make_item(item_i["i_d"], 1, session.player_id)
                instance_id = item.main_item.armor.instance_id
            else:
                weapon_len = len(res["Weapon"]["weapon"]["datas"])
                item_i = res["Weapon"]["weapon"]["datas"][
                    random.randint(0, weapon_len - 1)
                ]
                item = make_item(item_i["i_d"], 1, session.player_id)
                instance_id = item.main_item.weapon.instance_id
            rsp.drop_item.items.add().CopyFrom(item)
            session.drop_items[rsp.drop_item.index] = (
                instance_id,
                item,
            )  # TODO 放临时背包
        session.send(MsgId.MonsterDeadRsp, rsp, packet_id)
