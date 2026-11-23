from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    Character,
    GetCollectItemIdsReq,
    GetCollectItemIdsRsp,
    ItemDetail,
    StatusCode,
)

import utils.db as db


@packet_handler(MsgId.GetCollectItemIdsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCollectItemIdsReq()
        req.ParseFromString(data)

        rsp = GetCollectItemIdsRsp()
        rsp.status = StatusCode.StatusCode_OK
        seen = set()
        for k in db.get_claimed(session.player_id, "got_ids"):
            if k.isdigit():
                iid = int(k)
                if iid not in seen:
                    seen.add(iid)
                    rsp.item_ids.append(iid)
        for blob in db.get_item_detail(session.player_id) or ():
            if not isinstance(blob, (bytes, bytearray)):
                continue  # 非 bytes 时原 ParseFromString 抛 TypeError, 跳过
            item = ItemDetail()
            item.ParseFromString(blob)
            iid = item.main_item.item_id
            if iid and iid not in seen:
                seen.add(iid)
                rsp.item_ids.append(iid)
        for chr_blob in db.get_characters(session.player_id):
            if not isinstance(chr_blob, (bytes, bytearray)):
                continue  # 同上: 非 bytes 跳过
            chr_msg = Character()
            chr_msg.ParseFromString(chr_blob)
            if chr_msg.character_id and chr_msg.character_id not in seen:
                seen.add(chr_msg.character_id)
                rsp.item_ids.append(chr_msg.character_id)

        session.send(MsgId.GetCollectItemIdsRsp, rsp, packet_id)  # 1997,1998
