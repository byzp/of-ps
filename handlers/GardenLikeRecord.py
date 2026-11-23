from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GardenLikeRecordReq, GardenLikeRecordRsp, StatusCode
import utils.db as db
import utils.garden_state as garden_state

"""
# 花园点赞记录 2205 2206
"""


@packet_handler(MsgId.GardenLikeRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenLikeRecordReq()
        req.ParseFromString(data)

        rsp = GardenLikeRecordRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 点赞记录已持久化到 player_kv
        for liker_id, like_num in garden_state.get_like_records(session.player_id):
            info = db.get_players_info(
                liker_id, "player_name,head,sign,team_leader_badge"
            )
            if not info:
                continue
            record = rsp.record.add()
            record.player_id = liker_id
            record.name = info[0] or ""
            record.head = info[1] or 0
            record.like_num = like_num
            record.sign = info[2] or ""
            record.team_leader_badge = info[3] or 0

        session.send(MsgId.GardenLikeRecordRsp, rsp, packet_id)  # 2205,2206
