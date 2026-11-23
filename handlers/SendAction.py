from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import SendActionReq, SendActionRsp, SendActionNotice, StatusCode
from server.scene_data import up_action

import time

import utils.db as db
from utils.res_loader import res
from utils import achieve_track


def _is_learned(player_id, action_id) -> bool:
    """该动作是否在有效期内被学习过(kv ns=actions)"""
    raw = db.get_kv(player_id, "actions", "ids", b"")
    now_ms = int(time.time() * 1000)
    for entry in raw.decode().split(","):
        if ":" in entry:
            aid, exp = entry.split(":")
            if int(aid) == action_id and int(exp) > now_ms:
                return True
    return False


@packet_handler(MsgId.SendActionReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SendActionReq()
        req.ParseFromString(data)

        # 动作须在 Action.action_info 配置内: 校验先于广播,
        # 非法动作不得污染同频道(原实现先广播后校验)
        _actions = {
            a["i_d"]
            for a in res.get("Action", {}).get("action_info", {}).get("datas", [])
        }
        rsp = SendActionRsp()
        if req.action_id and _actions and req.action_id not in _actions:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.SendActionRsp, rsp, packet_id)
            return

        tmp = SendActionNotice()
        tmp.status = StatusCode.StatusCode_OK
        tmp.action_id = req.action_id
        tmp.from_player_id = session.player_id
        tmp.from_player_name = session.player_name
        # 已通过 ActionStudy 学习且未过期的动作标记为 is_study
        tmp.is_study = _is_learned(session.player_id, req.action_id)

        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.SendActionRsp, rsp, packet_id)
        achieve_track.report(session, "social_action", match=req.action_id)
        up_action(
            session.scene_id,
            session.channel_id,
            tmp,
        )
