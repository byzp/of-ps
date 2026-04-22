from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import random
import time

from proto.net_pb2 import FishingReq, FishingRsp, StatusCode, FishingResultNotice

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FishingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FishingReq()
        req.ParseFromString(data)

        rsp = FishingRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.is_cancel = req.is_cancel
        session.fishing = req.is_cancel == 0
        rsp.fishing_event_result.cost_endurance = 5
        total_time = random.randint(3, 20)
        rsp.fishing_event_result.cost_time = total_time
        while total_time > 1:
            event = rsp.fishing_event_result.fishing_event_list.add()
            event_s = random.sample(res["Fishing"]["fishing_event"]["datas"], 1)[0]
            event.i_d = event_s["i_d"]
            event.index = random.sample(event_s["fishing_event_items"], 1)[0]["index"]
            total_time -= 5
        has_fish = random.randint(0, 1)
        if has_fish:  # TODO 成就, 材料扣除, 额外鱼竿耐久扣除
            fish_id = random.sample(res["Fishing"]["fishing_info"]["datas"], 1)[0][
                "i_d"
            ]
            fish = rsp.fishing_event_result.fish_infos.add()
            fish.i_d = fish_id
            fish.length = random.uniform(1, 200)
        session.send(MsgId.FishingRsp, rsp, packet_id)  # 1397,1398

        time.sleep(rsp.fishing_event_result.cost_time)
        if session.fishing:
            rsp = FishingResultNotice()

            if has_fish:
                fish = rsp.items.add()
                fish_b = db.get_item_detail(session.player_id, fish_id)
                if fish_b:
                    fish.ParseFromString(fish_b)
                else:
                    make_item(fish_id, 0, session.player_id, fish)
                    fish.main_item.is_new = True
                fish.main_item.base_item.num += 1
                db.set_item_detail(session.player_id, fish.SerializeToString(), fish_id)

                item = rsp.items.add()
                item_b = db.get_item_detail(session.player_id, 11)  # 精力
                item.ParseFromString(item_b)
                item.main_item.base_item.num -= 1
                db.set_item_detail(session.player_id, item.SerializeToString(), 11)

            rsp.status = StatusCode.StatusCode_OK
            session.send(MsgId.FishingResultNotice, rsp, packet_id)
