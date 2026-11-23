from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangeHeadReq, ChangeHeadRsp, StatusCode

import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.ChangeHeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHeadReq()
        req.ParseFromString(data)

        rsp = ChangeHeadRsp()

        # 头像必须在 Head.head 配置内
        _heads = {
            h.get("head_i_d")
            for h in res.get("Head", {}).get("head", {}).get("datas", [])
            if h.get("is_show")
        }
        if _heads and req.head not in _heads:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ChangeHeadRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.head = req.head

        session.avatar_id = req.head
        db.set_players_info(session.player_id, "head", session.avatar_id)

        session.send(MsgId.ChangeHeadRsp, rsp, packet_id)  # 更换头像 1528 1529
