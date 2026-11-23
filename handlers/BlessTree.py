from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BlessTreeReq,
    BlessTreeRsp,
    StatusCode,
)

import utils.db as db

"""
# 祈福树信息查询 2585 2586
# 返回该祈福树已解锁的节点列表, 解锁见 BlessTreeUnlock.py
"""


@packet_handler(MsgId.BlessTreeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BlessTreeReq()
        req.ParseFromString(data)

        rsp = BlessTreeRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.def_id = req.def_id

        # def_id 为 0 时 db.get_bless_tree 返回 {def_id: [tree_ids]} 字典而非列表, 需过滤
        tree_ids = (
            db.get_bless_tree(session.player_id, req.def_id) if req.def_id else []
        )
        rsp.tress.tree_ids.extend(tree_ids)  # proto 里字段名就叫 tress

        session.send(MsgId.BlessTreeRsp, rsp, packet_id)  # 2585,2586
