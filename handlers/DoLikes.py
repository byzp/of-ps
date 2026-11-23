from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import DoLikesReq, DoLikesRsp, StatusCode
import utils.db as db
import utils.garden_state as garden_state
from utils import achieve_track

"""
# 花园点赞 1693 1694
"""


@packet_handler(MsgId.DoLikesReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DoLikesReq()
        req.ParseFromString(data)

        rsp = DoLikesRsp()

        # 玩家当前所在频道即花园主人的 player_id
        target_id = session.channel_id

        left = garden_state.consume_like(session.player_id)
        if left is None:
            # 今日点赞次数已用尽
            rsp.status = StatusCode.StatusCode_TIPS_LIKES_NUM_LIMIT
            rsp.left_like_nums = 0
            row = db.get_players_info(target_id, "garden_like_num")
            rsp.like_nums = (row[0] or 0) if row else 0
            session.send(MsgId.DoLikesRsp, rsp, packet_id)  # 1693,1694
            return

        rsp.status = StatusCode.StatusCode_OK
        # 成就: 为他人的花园点赞
        achieve_track.report(session, "like_garden")

        # players 表累计总赞数
        row = db.get_players_info(target_id, "garden_like_num")
        like_nums = ((row[0] or 0) if row else 0) + 1
        db.set_players_info(target_id, "garden_like_num", like_nums)

        # garden_info 表同步
        _, access_num, furniture_num, furniture_limit_num, is_open = db.get_garden_info(
            target_id
        )
        db.set_garden_info(
            target_id,
            like_nums,
            access_num,
            furniture_num,
            furniture_limit_num,
            is_open,
        )

        # 点赞记录(GardenLikeRecord 使用)
        garden_state.add_like_record(target_id, session.player_id)

        rsp.left_like_nums = left
        rsp.like_nums = like_nums

        session.send(MsgId.DoLikesRsp, rsp, packet_id)  # 1693,1694
