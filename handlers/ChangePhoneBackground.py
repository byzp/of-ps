from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangePhoneBackgroundReq, ChangePhoneBackgroundRsp, StatusCode

import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.ChangePhoneBackgroundReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePhoneBackgroundReq()
        req.ParseFromString(data)

        rsp = ChangePhoneBackgroundRsp()

        # 背景与手机壳共用 Phone 表
        _cases = {
            p["i_d"] for p in res.get("Phone", {}).get("phone", {}).get("datas", [])
        }
        if _cases and req.phone_background not in _cases:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ChangePhoneBackgroundRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK

        rsp.phone_background = req.phone_background
        db.set_players_info(session.player_id, "phone_background", req.phone_background)

        session.send(
            MsgId.ChangePhoneBackgroundRsp, rsp, packet_id
        )  # 更换手机背景 1517 1518
