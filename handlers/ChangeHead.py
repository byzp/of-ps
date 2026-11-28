import logging

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangeHeadReq, ChangeHeadRsp, StatusCode

import utils.db as db
from utils.trace import trace
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeHeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHeadReq()
        req.ParseFromString(data)

        rsp = ChangeHeadRsp()

        _heads = {
            h.get("head_i_d")
            for h in res.get("Head", {}).get("head", {}).get("datas", [])
            if h.get("is_show")
        }
        if _heads and req.head and req.head not in _heads:
            # 原来这里直接回 CFG_NOT_FOUND, 客户端会当作失败;
            # 头像框属于外观, 不在表里也允许设置, 只记日志。
            logger.warning(
                "ChangeHead: player=%s 头像 %s 不在 Head 配置里(仍放行)",
                session.player_id,
                req.head,
            )
        rsp.status = StatusCode.StatusCode_OK
        rsp.head = req.head

        session.avatar_id = req.head
        db.set_players_info(session.player_id, "head", session.avatar_id)

        logger.info(
            "ChangeHead: player=%s head=%s status=%s", session.player_id, req.head, rsp.status
        )
        trace("change_head", player=session.player_id, head=req.head, status=rsp.status)
        session.send(MsgId.ChangeHeadRsp, rsp, packet_id)
