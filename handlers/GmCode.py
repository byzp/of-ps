from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GmCodeReq, GmCodeRsp, StatusCode

logger = logging.getLogger(__name__)

"""
# GM代码处理 1013 1014
"""


@packet_handler(MsgId.GmCodeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GmCodeReq()
        req.ParseFromString(data)
        print(req)

        rsp = GmCodeRsp()
        rsp.status = StatusCode.StatusCode_OK

        # # 设置响应结果
        # rsp.result = f"GM command '{req.param}' executed successfully"

        # # 添加在线玩家列表
        # rsp.online_players.append(session.player_id)

        session.send(MsgId.GmCodeRsp, rsp, packet_id)
