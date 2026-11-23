from config import Config
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    ActionStudyReq,
    ActionStudyRsp,
    ActionStudyNotice,
    AchieveActionUnLockNotice,
    StatusCode,
)
from server.scene_data import get_session

import utils.db as db


@packet_handler(MsgId.ActionStudyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActionStudyReq()
        req.ParseFromString(data)

        rsp = ActionStudyRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.ActionStudyRsp, rsp, packet_id)  # 2209,2210

        # 向同场景频道玩家广播学习动作
        notice = ActionStudyNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.player_id = session.player_id
        notice.name = session.player_name
        notice.action_id = req.action_id
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.ActionStudyNotice, notice, 0)  # 2212

        # 学到的动作持久化(kv ns=actions, 值为过期时间戳毫秒), 时限 24 小时
        expire_ms = int((time.time() + Config.ACTION_VALID_SECONDS) * 1000)
        raw = db.get_kv(session.player_id, "actions", "ids", b"")
        actions = {}
        now_ms = int(time.time() * 1000)
        for entry in raw.decode().split(","):
            if ":" in entry:
                aid, exp = entry.split(":")
                if int(exp) > now_ms:  # 清理过期项
                    actions[int(aid)] = int(exp)
        actions[req.action_id] = expire_ms
        db.set_kv(
            session.player_id,
            "actions",
            "ids",
            ",".join(f"{a}:{e}" for a, e in sorted(actions.items())).encode(),
        )

        unlock = AchieveActionUnLockNotice()
        unlock.status = StatusCode.StatusCode_OK
        unlock.study_action[req.action_id] = expire_ms
        session.send(MsgId.AchieveActionUnLockNotice, unlock, 0)  # 2010
