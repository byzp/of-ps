from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import FriendIntervalInitReq, FriendIntervalInitRsp, StatusCode

"""
# 好友间隙初始化 1841 1842
"""


@packet_handler(MsgId.FriendIntervalInitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendIntervalInitReq()
        req.ParseFromString(data)

        rsp = FriendIntervalInitRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.FriendIntervalInitRsp, rsp, packet_id)
