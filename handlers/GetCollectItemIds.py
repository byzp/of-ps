from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as GetCollectItemIdsReq_pb2
import proto.OverField_pb2 as GetCollectItemIdsRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.GetCollectItemIdsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCollectItemIdsReq_pb2.GetCollectItemIdsReq()
        req.ParseFromString(data)

        rsp = GetCollectItemIdsRsp_pb2.GetCollectItemIdsRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO item_ids
        session.send(MsgId.GetCollectItemIdsRsp, rsp, packet_id)  # 1997,1998
