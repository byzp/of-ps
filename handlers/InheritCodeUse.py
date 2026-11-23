from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    InheritCodeUseReq,
    InheritCodeUseRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db

"""
# 使用继承码 3001 3002
继承码用于跨渠道/换端继承账号奖励, 码库由 GM 写入 db.redeem_codes(code_type='inherit')。
"""


@packet_handler(MsgId.InheritCodeUseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = InheritCodeUseReq()
        req.ParseFromString(data)

        rsp = InheritCodeUseRsp()
        rsp.code_str = req.code

        status, rewards_str = db.use_redeem_code(
            session.player_id, req.code, code_type="inherit"
        )
        if status != 0:
            rsp.status = StatusCode.StatusCode_REDEMPTION_CODE_NOT_EXIST
            session.send(MsgId.InheritCodeUseRsp, rsp, packet_id)  # 3001,3002
            return

        reward_list = []
        for pair in rewards_str.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            item_id_str, num_str = pair.split(":", 1)
            if not (item_id_str.strip().isdigit() and num_str.strip().isdigit()):
                continue
            item_id = int(item_id_str)
            num = int(num_str)
            if item_id and num > 0:
                reward_list.append((item_id, num))

        rsp.status = StatusCode.StatusCode_OK
        if reward_list:
            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            db.grant_rewards(session.player_id, reward_list, rsp.rewards, pack)
            session.send(MsgId.PackNotice, pack, 0)

        session.send(MsgId.InheritCodeUseRsp, rsp, packet_id)  # 3001,3002
