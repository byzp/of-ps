from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetCollectItemIdsReq, GetCollectItemIdsRsp, StatusCode


@packet_handler(MsgId.GetCollectItemIdsReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCollectItemIdsReq()
        req.ParseFromString(data)

        rsp = GetCollectItemIdsRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO item_ids
        session.send(MsgId.GetCollectItemIdsRsp, rsp, packet_id)  # 1997,1998
