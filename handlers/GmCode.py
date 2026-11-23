from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GmCodeReq, GmCodeRsp, StatusCode

import utils.db as db

"""
# GM代码处理 1013 1014
# 本地私服调试指令(远端官方返回 FAIL, 不对齐):
#   level <n>  设置玩家等级(1-60)
"""


@packet_handler(MsgId.GmCodeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GmCodeReq()
        req.ParseFromString(data)

        rsp = GmCodeRsp()
        rsp.status = StatusCode.StatusCode_OK

        parts = (req.param or "").split()
        if len(parts) == 2 and parts[0] == "level":
            _p = parts[1]
            _body = _p[1:] if _p[:1] in ("+", "-") else _p
            if _body.isdigit():
                lv = max(1, min(60, int(_p)))
                db.set_players_info(session.player_id, "level", lv)

        session.send(MsgId.GmCodeRsp, rsp, packet_id)
