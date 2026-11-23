from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangePhoneCaseReq, ChangePhoneCaseRsp, StatusCode

import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.ChangePhoneCaseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePhoneCaseReq()
        req.ParseFromString(data)

        rsp = ChangePhoneCaseRsp()

        _cases = {
            p["i_d"] for p in res.get("Phone", {}).get("phone", {}).get("datas", [])
        }
        if _cases and req.phone_case not in _cases:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ChangePhoneCaseRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.phone_case = req.phone_case

        # 手机壳持久化(players 表无对应列, 存 kv ns=player)
        db.set_kv(session.player_id, "player", "phone_case", int(req.phone_case))

        session.send(MsgId.ChangePhoneCaseRsp, rsp, packet_id)  # 更换手机壳 1539 1540
