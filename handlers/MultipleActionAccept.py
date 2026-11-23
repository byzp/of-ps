from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    MultipleActionAcceptReq,
    MultipleActionAcceptRsp,
    SendMultipleActionCompleteNotice,
    StatusCode,
)
import utils.db as db
from utils.res_loader import res
from server.scene_data import get_session


@packet_handler(MsgId.MultipleActionAcceptReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MultipleActionAcceptReq()
        req.ParseFromString(data)

        rsp = MultipleActionAcceptRsp()

        # 亲密度门槛(Expression.multiplayer_expression: starter 动作 -> intimacy_limit,
        # -1 表示无限制; 达标才接受双人动作邀请)
        row = next(
            (
                e
                for e in res["Expression"]["multiplayer_expression"]["datas"]
                if isinstance(e, dict)
                and e.get("starter_play_action_i_d") == req.action_id
            ),
            None,
        )
        limit = int(row.get("intimacy_limit", -1)) if row else -1
        if limit >= 0:
            _friend = db.get_friend_info(
                session.player_id, req.from_player_id, "friend_intimacy"
            )
            intimacy = _friend[0] if _friend else 0
            if intimacy < limit:
                rsp.status = StatusCode.StatusCode_FRIEND_INTIMACY_NOT_ENOUGH
                session.send(MsgId.MultipleActionAcceptRsp, rsp, packet_id)
                return

        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.MultipleActionAcceptRsp, rsp, packet_id)  # 1977,1978

        # 接受多人动作邀请后, 向同场景频道广播动作达成
        if req.status == StatusCode.StatusCode_OK:
            notice = SendMultipleActionCompleteNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.action_id = req.action_id
            notice.from_player_id = req.from_player_id
            notice.action_player_ids.append(req.from_player_id)
            notice.action_player_ids.append(session.player_id)
            for s in get_session():
                if (
                    s.scene_id == session.scene_id
                    and s.channel_id == session.channel_id
                ):
                    s.send(MsgId.SendMultipleActionCompleteNotice, notice, 0)  # 1980
