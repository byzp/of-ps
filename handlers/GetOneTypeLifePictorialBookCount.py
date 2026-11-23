from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import utils.db as db

from proto.net_pb2 import (
    GetOneTypeLifePictorialBookCountReq,
    GetOneTypeLifePictorialBookCountRsp,
    StatusCode,
)


@packet_handler(MsgId.GetOneTypeLifePictorialBookCountReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetOneTypeLifePictorialBookCountReq()
        req.ParseFromString(data)

        rsp = GetOneTypeLifePictorialBookCountRsp()
        rsp.status = StatusCode.StatusCode_OK
        # 生活图鉴计数: 各制作成功时按 "类型:物品id" 累计(kv ns=life_book)。
        prefix = str(req.life_type) + ":"
        for k in db.get_kv_keys(session.player_id, "life_book"):
            if not k.startswith(prefix):
                continue
            entry = rsp.life_achieve_count_lst.add()
            entry.id = int(k[len(prefix) :])
            entry.count = int(db.get_kv(session.player_id, "life_book", k, 0) or 0)
        session.send(
            MsgId.GetOneTypeLifePictorialBookCountRsp, rsp, packet_id
        )  # 1365,1366
