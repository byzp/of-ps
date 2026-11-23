from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    InviteCodeUseReq,
    InviteCodeUseRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res

"""
# 填写邀请码 2254 2255
被邀请人奖励来源 ActivityInvite.json activity_invite.activity_invite_item
(表内 6001/6002 两期配置相同: 104×1, 102×30, 101×5000);
请求不带活动 id, 取表内第一期配置
"""


def _invite_code_rewards():
    for row in (
        res.get("ActivityInvite", {}).get("activity_invite", {}).get("datas") or ()
    ):
        rewards = [
            (r["item_i_d"], r.get("item_num", 0))
            for r in row.get("activity_invite_item", ()) or ()
            if r.get("item_i_d") and r.get("item_num", 0) > 0
        ]
        if rewards:
            return rewards
    return Config.INVITE_CODE_REWARDS_FALLBACK


@packet_handler(MsgId.InviteCodeUseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = InviteCodeUseReq()
        req.ParseFromString(data)

        rsp = InviteCodeUseRsp()

        if not req.code:
            rsp.status = StatusCode.StatusCode_INVITE_CODE_NOT_EXIST
            session.send(MsgId.InviteCodeUseRsp, rsp, packet_id)  # 2254,2255
            return

        # 邀请码登记于 kv(全局 ns=invite): 同一码全局仅一人可用, 每人仅填一次
        owner = db.get_kv(0, "invite", f"owner:{req.code}")
        if owner and int(owner) != session.player_id:
            rsp.status = StatusCode.StatusCode_INVITE_CODE_ALREADY_FILLED
            session.send(MsgId.InviteCodeUseRsp, rsp, packet_id)  # 2254,2255
            return
        if db.get_kv(session.player_id, "invite", "used"):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.InviteCodeUseRsp, rsp, packet_id)  # 2254,2255
            return

        rsp.status = StatusCode.StatusCode_OK

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        db.set_kv(0, "invite", f"owner:{req.code}", str(session.player_id))
        db.set_kv(session.player_id, "invite", "used", b"1")
        db.grant_rewards(session.player_id, _invite_code_rewards(), rsp.rewards, pack)

        session.send(MsgId.InviteCodeUseRsp, rsp, packet_id)  # 2254,2255
        session.send(MsgId.PackNotice, pack, 0)
