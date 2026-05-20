from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import WishListByFriendIdRsp, StatusCode


@packet_handler(MsgId.WishListByFriendIdReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = WishListByFriendIdRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO
        session.send(MsgId.WishListByFriendIdRsp, rsp, packet_id)  # 2685,2686
