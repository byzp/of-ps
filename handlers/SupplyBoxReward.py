from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random
import time

from proto.net_pb2 import (
    SupplyBoxRewardReq,
    SupplyBoxRewardRsp,
    StatusCode,
    PackNotice,
)
from utils.res_loader import res
from utils import item_mgr
import utils.db as db
from utils import achieve_track
from utils import supply_box

"""
# 补给箱领奖 1893 1894
刷新间隔(已对表验证): GlobalConfig key=SupplyBox_Random_Time values=('10','30'),
单位分钟, 下次可领时间取 10-30 分钟随机, 持久化于 kv ns=player k=supply_box_next。
注: 奖励内容无表可查 —— 已查 GlobalConfig 全部 316 个键、Treasure.json、
TreasureBox.json、QuickObtaining.json、RandomEvent.json 及全资源目录 supply
关键字均无补给箱奖励配置(应在服务端私有配置, 未随客户端资源下发),
维持金币101 x1000 占位。
"""


@packet_handler(MsgId.SupplyBoxRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SupplyBoxRewardReq()
        req.ParseFromString(data)

        rsp = SupplyBoxRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 冷却校验: 未到 next_reward_time 不重复发放
        now = int(time.time())
        next_ts = supply_box.next_reward_time(session.player_id)
        if now < next_ts:
            rsp.status = StatusCode.StatusCode_FAIL
            rsp.next_reward_time = next_ts
            session.send(MsgId.SupplyBoxRewardRsp, rsp, packet_id)  # 1893,1894
            return

        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                [(Config.SUPPLY_BOX_COIN_ITEM_ID, Config.SUPPLY_BOX_COIN_COUNT)],
                rsp_items=rsp.items,
                pack_notice=pack,
                session=session,
            )
            rsp.next_reward_time = now + supply_box.interval_seconds()
            db.set_kv(
                session.player_id, "player", "supply_box_next", rsp.next_reward_time
            )
            achieve_track.report(session, "supply_box")
            session.send(MsgId.SupplyBoxRewardRsp, rsp, packet_id)
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
