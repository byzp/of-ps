from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
from proto.net_pb2 import GetAllCharacterEquipReq, GetAllCharacterEquipRsp, StatusCode
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetAllCharacterEquipReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetAllCharacterEquipReq()
        req.ParseFromString(data)

        rsp = GetAllCharacterEquipRsp()
        rsp.status = StatusCode.StatusCode_OK

        items_data = db.get_item_detail(session.player_id, table="items_s")
        if items_data:
            for item_blob in items_data:
                item = rsp.items.add()
                item.ParseFromString(item_blob)

        session.send(
            MsgId.GetAllCharacterEquipRsp, rsp, packet_id
        )  # 打开探索员界面响应全部装备
