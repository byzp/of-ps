from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetAllCharacterEquipReq,
    GetAllCharacterEquipRsp,
    StatusCode,
    ItemDetail,
)
import utils.db as db


@packet_handler(MsgId.GetAllCharacterEquipReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetAllCharacterEquipReq()
        req.ParseFromString(data)

        rsp = GetAllCharacterEquipRsp()
        rsp.status = StatusCode.StatusCode_OK

        items_data = db.get_item_detail(session.player_id, table="items_s")
        team = db.get_players_info(session.player_id, "team")[0]
        if items_data:
            for item_blob in items_data:
                item = ItemDetail()
                item.ParseFromString(item_blob)
                kind = item.main_item.WhichOneof("item")
                if kind not in ("weapon", "armor", "poster"):
                    continue
                wearer = getattr(item.main_item, kind).wearer_id
                # 在场角色的装备已由登录/队伍同步提供，此接口补后备角色装备。
                if wearer and wearer not in team:
                    rsp.items.add().CopyFrom(item)

        session.send(
            MsgId.GetAllCharacterEquipRsp, rsp, packet_id
        )  # 打开探索员界面响应全部装备
