from config import Config
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import MonthCardRewardReq, MonthCardRewardRsp, StatusCode

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils import refresh


@packet_handler(MsgId.MonthCardRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MonthCardRewardReq()
        req.ParseFromString(data)

        rsp = MonthCardRewardRsp()

        over_due_time = db.get_month_card_over_due_time(session.player_id)
        reward_days = db.get_month_card_reward_days(session.player_id)

        if over_due_time <= int(time.time()):
            # 月卡已过期, 不能领取
            rsp.status = StatusCode.StatusCode_FAIL
            rsp.month_card_reward_days = reward_days
            session.send(MsgId.MonthCardRewardRsp, rsp, packet_id)  # 2309 2310
            return

        # 按天去重: db.try_claim 原子判重, kv ns=month_card 记录最后领取日
        day = str(refresh.day_index())
        if not db.try_claim(session.player_id, "month_card", day):
            rsp.status = StatusCode.StatusCode_MOON_CARD_DAYS_LIMIT
            rsp.month_card_reward_days = reward_days
            session.send(MsgId.MonthCardRewardRsp, rsp, packet_id)  # 2309 2310
            return
        db.set_kv(session.player_id, "month_card", "last_claim_day", day)

        reward_days += 1
        db.set_month_card_reward_days(session.player_id, reward_days)

        rsp.status = StatusCode.StatusCode_OK
        rsp.month_card_reward_days = reward_days

        reward_item_id, reward_num = Config.MONTH_CARD_REWARD_FALLBACK
        for e in res["GlobalConfig"]["config"]["datas"]:
            if not isinstance(e, dict):
                continue
            if e.get("key") == "MoonCard_Rveryday_Currency":
                values = e.get("values") or ()
                if values and isinstance(values[0], str):
                    parts = values[0].split(":")
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        reward_item_id, reward_num = int(parts[0]), int(parts[1])
                break
        item_mgr.grant_items(
            session.player_id, [(reward_item_id, reward_num)], session=session
        )

        session.send(MsgId.MonthCardRewardRsp, rsp, packet_id)  # 月卡每日奖励 2309 2310
