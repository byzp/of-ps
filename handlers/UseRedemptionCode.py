from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    UseRedemptionCodeReq,
    UseRedemptionCodeRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db

"""
# 使用兑换码 2151 2152
兑换码库由 GM 命令写入 db.redeem_codes 表, 此处调用 db.use_redeem_code 核销。
"""


@packet_handler(MsgId.UseRedemptionCodeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UseRedemptionCodeReq()
        req.ParseFromString(data)

        rsp = UseRedemptionCodeRsp()
        rsp.code = req.code

        status, rewards_str = db.use_redeem_code(session.player_id, req.code)
        if status != 0:
            # 1=码不存在, 2=已过期, 3=次数用尽, 4=该玩家已用过
            rsp.status = StatusCode.StatusCode_REDEMPTION_CODE_NOT_EXIST
            session.send(MsgId.UseRedemptionCodeRsp, rsp, packet_id)  # 2151,2152
            return

        # 解析奖励 "item_id:num,item_id:num,..."
        reward_list = []
        for pair in rewards_str.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            item_id_str, num_str = pair.split(":", 1)
            if not isinstance(item_id_str, (int, str)) or not isinstance(
                num_str, (int, str)
            ):
                continue
            if (
                isinstance(item_id_str, str)
                and not item_id_str.strip().lstrip("+-").isdigit()
            ):
                continue
            if isinstance(num_str, str) and not num_str.strip().lstrip("+-").isdigit():
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

        session.send(MsgId.UseRedemptionCodeRsp, rsp, packet_id)  # 2151,2152
