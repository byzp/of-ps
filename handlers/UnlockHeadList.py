from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as UnlockHeadListReq_pb2
import proto.OverField_pb2 as UnlockHeadListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.UnlockHeadListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UnlockHeadListReq_pb2.UnlockHeadListReq()
        req.ParseFromString(data)

        rsp = UnlockHeadListRsp_pb2.UnlockHeadListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        heads = []
        item = pb.ItemDetail()
        for i in db.get_item_detail(session.player_id):
            item.ParseFromString(i)
            if item.main_item.item_tag == pb.EBagItemTag_Head:
                heads.append(item.main_item.item_id)
        rsp.heads.extend(heads)

        session.send(
            MsgId.UnlockHeadListRsp, rsp, packet_id
        )  # 获取已解锁头像列表 1529 1530
