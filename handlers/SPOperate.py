from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import SPOperateReq, SPOperateRsp, SPOperateType, StatusCode

import server.photo_share as ps
from utils.res_loader import res

logger = logging.getLogger(__name__)


def _password_length():
    """SP 二级密码长度(GlobalConfig.SecondaryVerificationPasswordLength)"""
    for e in res["GlobalConfig"]["config"]["datas"]:
        if e.get("key") == "SecondaryVerificationPasswordLength":
            return int(e["values"][0])
        pass
    return 6


@packet_handler(MsgId.SPOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SPOperateReq()
        req.ParseFromString(data)

        rsp = SPOperateRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.operate_type = req.operate_type

        # SP 推测为隐私空间/二级密码: Open 设置密码, Change 改密, Check 校验, Close 关闭
        # 状态经 photo_share 快照持久化
        with ps.lock_sp:
            state = ps.sp_state.setdefault(
                session.player_id, {"password": "", "open": False}
            )
            match req.operate_type:
                case SPOperateType.SPOperateType_Open:
                    if len(req.password) != _password_length():
                        rsp.status = StatusCode.StatusCode_FAIL
                        rsp.sp_check_status = False
                    else:
                        state["password"] = req.password
                        state["open"] = True
                        rsp.sp_check_status = True
                case SPOperateType.SPOperateType_Change:
                    if state["password"] and req.old_password != state["password"]:
                        rsp.status = StatusCode.StatusCode_FAIL
                        rsp.sp_check_status = False
                    else:
                        state["password"] = req.password
                        rsp.sp_check_status = True
                case SPOperateType.SPOperateType_Check:
                    rsp.sp_check_status = req.password == state["password"]
                    if not rsp.sp_check_status:
                        rsp.status = StatusCode.StatusCode_FAIL
                case SPOperateType.SPOperateType_Close:
                    if state["password"] and req.password != state["password"]:
                        rsp.status = StatusCode.StatusCode_FAIL
                        rsp.sp_check_status = False
                    else:
                        state["open"] = False
                        state["password"] = ""
                        rsp.sp_check_status = True
                case _:
                    logger.info("SPOperateReq 未知 operate_type=%s", req.operate_type)
            rsp.sp_open_status = state["open"]

        session.send(MsgId.SPOperateRsp, rsp, packet_id)  # 2695,2696
