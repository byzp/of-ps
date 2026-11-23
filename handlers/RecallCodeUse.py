from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    RecallCodeUseReq,
    RecallCodeUseRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db

"""
# 使用回归召回码 4513 4514
老玩家把召回码发给回归玩家(或反之)兑换奖励, 码库由 GM 写入 db.redeem_codes(code_type='recall')。
"""


@packet_handler(MsgId.RecallCodeUseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RecallCodeUseReq()
        req.ParseFromString(data)

        rsp = RecallCodeUseRsp()

        status, rewards_str = db.use_redeem_code(
            session.player_id, req.code, code_type="recall"
        )
        if status != 0:
            rsp.status = StatusCode.StatusCode_REDEMPTION_CODE_NOT_EXIST
            session.send(MsgId.RecallCodeUseRsp, rsp, packet_id)  # 4513,4514
            return

        reward_list = []
        for pair in rewards_str.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            item_id_str, num_str = pair.split(":", 1)
            if not (item_id_str.isdigit() and num_str.isdigit()):
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

        session.send(MsgId.RecallCodeUseRsp, rsp, packet_id)  # 4513,4514
