from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TempPackSortReq,
    TempPackSortRsp,
    StatusCode,
    ItemDetail,
)

from utils import item_mgr


@packet_handler(MsgId.TempPackSortReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TempPackSortReq()
        req.ParseFromString(data)

        rsp = TempPackSortRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 按物品ID排序后重排临时背包索引
        entries = []
        for instance_id, blob in session.temp_pack:
            item = ItemDetail()
            item.ParseFromString(blob)
            entries.append((instance_id, item))
        entries.sort(key=lambda e: e[1].main_item.item_id)

        rsp.temp_pack.max_size = Config.TEMP_PACK_MAX
        new_pack = []
        for i, (instance_id, item) in enumerate(entries):
            item.main_item.temp_pack_index = i + 1
            new_pack.append((instance_id, item.SerializeToString()))
            rsp.temp_pack.item_infos.add().CopyFrom(item.main_item)
        session.temp_pack[:] = new_pack

        session.send(MsgId.TempPackSortRsp, rsp, packet_id)  # 1411,1412
