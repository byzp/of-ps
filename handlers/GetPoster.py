from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    GetPosterReq,
    GetPosterRsp,
    StatusCode,
    ItemDetail,
    EBagItemTag,
)

import utils.db as db


@packet_handler(MsgId.GetPosterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetPosterReq()
        req.ParseFromString(data)

        rsp = GetPosterRsp()
        rsp.status = StatusCode.StatusCode_OK

        posters = []
        for item in db.get_item_detail(session.player_id, table="items_s"):
            tmp = ItemDetail()
            tmp.ParseFromString(item)
            if tmp.main_item.item_tag == EBagItemTag.EBagItemTag_Poster:
                posters.append(tmp.main_item.poster)
        start = max(0, req.start_index)
        end = req.end_index or len(posters)
        rsp.posters.extend(posters[start:end])
        rsp.total_num = len(posters)
        rsp.end_index = min(end, len(posters))

        session.send(MsgId.GetPosterRsp, rsp, packet_id)  # 获取映像列表 1405 1406
