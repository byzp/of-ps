from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TempPackItemDropReq,
    TempPackItemDropRsp,
    StatusCode,
    ItemDetail,
)

import utils.db as db
from utils import item_mgr


@packet_handler(MsgId.TempPackItemDropReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TempPackItemDropReq()
        req.ParseFromString(data)

        rsp = TempPackItemDropRsp()
        rsp.status = StatusCode.StatusCode_OK

        idx = req.index  # temp_pack_index 从1开始(见 TreasureBoxPickup)
        if idx < 1 or idx > len(session.temp_pack):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.TempPackItemDropRsp, rsp, packet_id)
            return

        instance_id, blob = session.temp_pack.pop(idx - 1)
        # 丢弃 = 同时删除拾取时预写入背包的持久化副本
        if instance_id:
            db.del_item_detail(session.player_id, instance_id)
        else:
            dropped = ItemDetail()
            dropped.ParseFromString(blob)
            item_mgr.consume_items(
                session.player_id,
                [(dropped.main_item.item_id, dropped.main_item.base_item.num)],
            )

        # 重排剩余临时背包索引并返回最新临时背包
        rsp.temp_pack.max_size = Config.TEMP_PACK_MAX
        new_pack = []
        for i, (iid, blob) in enumerate(session.temp_pack):
            item = ItemDetail()
            item.ParseFromString(blob)
            item.main_item.temp_pack_index = i + 1
            new_pack.append((iid, item.SerializeToString()))
            rsp.temp_pack.item_infos.add().CopyFrom(item.main_item)
        session.temp_pack[:] = new_pack

        session.send(MsgId.TempPackItemDropRsp, rsp, packet_id)  # 1407,1408
