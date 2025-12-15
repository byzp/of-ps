from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetPosterReq_pb2
import proto.OverField_pb2 as GetPosterRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetPosterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetPosterReq_pb2.GetPosterReq()
        req.ParseFromString(data)

        rsp = GetPosterRsp_pb2.GetPosterRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        max_num = req.end_index - req.start_index
        total_num = 0

        for item in db.get_item_detail(session.player_id):
            tmp = pb.ItemDetail()
            tmp.ParseFromString(item)
            if tmp.main_item.item_tag == pb.EBagItemTag_Poster:
                if max_num == total_num:
                    break
                total_num += 1
                rsp.posters.add().CopyFrom(tmp.main_item.poster)

        rsp.total_num = total_num
        rsp.end_index = req.start_index + total_num

        session.send(MsgId.GetPosterRsp, rsp, packet_id)  # 获取映像列表 1405 1406
