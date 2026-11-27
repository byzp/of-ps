from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import PopEmojiReq, PopEmojiRsp, PopEmojiNotice, StatusCode
from server import shared_projection
from server.scene_data import get_session
from utils import achieve_track
import utils.db as db


@packet_handler(MsgId.PopEmojiReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PopEmojiReq()
        req.ParseFromString(data)

        rate_limiter = getattr(session, "rate_limiter", None)
        if rate_limiter is not None and not rate_limiter.allow("emoji"):
            session.send(
                MsgId.PopEmojiRsp,
                PopEmojiRsp(status=StatusCode.StatusCode_REQUESTS_TOO_FREQUENT),
                packet_id,
            )
            return

        rsp = PopEmojiRsp()
        shared_projection.store.record_emoji(
            session.player_id,
            session.scene_id,
            session.channel_id,
            req.emoji_id,
        )

        # 向同场景频道玩家广播冒表情
        notice = PopEmojiNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.emoji_id = req.emoji_id
        notice.from_player_id = session.player_id
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.PopEmojiNotice, notice, 0)  # 1910

        rsp.status = StatusCode.StatusCode_OK
        # 成就: 发送任意表情
        achieve_track.report(session, "send_emoji")
        session.send(MsgId.PopEmojiRsp, rsp, packet_id)  # 1911,1912
