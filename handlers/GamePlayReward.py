from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GamePlayRewardReq, GamePlayRewardRsp, StatusCode
import utils.db as db
from utils.res_loader import res

"""
# 玩法领奖 1451 1452(官方抓包 6/6 样本实锤)
回包仅 status + dynamic_treasure_box_info{box_id, index} —— 不发任何
items, 奖励全部装进生成的动态宝箱, 由客户端 TreasureBoxOpenReq
(loc_type=DYNAMIC, treasure_box_index=index) 开箱领取。
box_id = reward_id + 2000(TreasureBox.game_treasure_box: 1001→3001,
1002→3002), 不在表内回 CFG_NOT_FOUND。index 与遭遇战/旗帜战宝箱共用
同一递增序号(kv ns=dyn_box, 官方登录会话 idx 1,2,3... 连续)。
"""


@packet_handler(MsgId.GamePlayRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GamePlayRewardReq()
        req.ParseFromString(data)

        rsp = GamePlayRewardRsp()

        box_id = req.reward_id + 2000
        known = any(
            e.get("i_d") == box_id
            for e in res.get("TreasureBox", {})
            .get("game_treasure_box", {})
            .get("datas", ())
        )
        if not known:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GamePlayRewardRsp, rsp, packet_id)  # 1451,1452
            return

        rsp.status = StatusCode.StatusCode_OK
        idx = db.incr_kv(session.player_id, "dyn_box", "seq")
        db.set_kv(session.player_id, "dyn_box", idx, box_id)
        rsp.dynamic_treasure_box_info.box_id = box_id
        rsp.dynamic_treasure_box_info.index = idx

        session.send(MsgId.GamePlayRewardRsp, rsp, packet_id)  # 1451,1452
