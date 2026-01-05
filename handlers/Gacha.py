from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import random

import proto.OverField_pb2 as GachaReq_pb2
import proto.OverField_pb2 as GachaRsp_pb2
import proto.OverField_pb2 as Pack_pb2

from utils.res_loader import res

logger = logging.getLogger(__name__)


"""
# 招募 1445 1446
"""


def get_gacha_info(gacha_id: int):
    for dat in res["Gacha"]["info"]["datas"]:
        if dat["i_d"] == gacha_id:
            return dat
    return None


def get_pool(pool_id: int):
    for dat in res["Gacha"]["pool"]["datas"]:
        if dat["i_d"] == pool_id:
            return dat
    return None


def get_reward_pool(reward_pool_id: int):
    for dat in res["Gacha"]["reward_pool"]["datas"]:
        if dat["i_d"] == reward_pool_id:
            return dat
    return None


def calc_extra_quality(item_id: int) -> int:
    # 按角色 ID 段位
    if item_id >= 400000:
        return 5
    elif item_id >= 200000:
        return 4
    else:
        return 3


@packet_handler(MsgId.GachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaReq_pb2.GachaReq()
        req.ParseFromString(data)
        logger.info(f"GachaReq => {req}")

        rsp = GachaRsp_pb2.GachaRsp()
        rsp.status = 1

        # 抽卡次数
        draw_times = 1 if req.is_single else 10

        # 找卡池配置
        gacha_info = get_gacha_info(req.gacha_id)
        if not gacha_info:
            logger.error(f"Gacha info not found: {req.gacha_id}")
            session.send(MsgId.GachaRsp, rsp, packet_id)
            return

        pool_id = gacha_info.get("big_guarantee_pool_i_d")
        pool = get_pool(pool_id)
        if not pool:
            logger.error(f"Gacha pool not found: {pool_id}")
            session.send(MsgId.GachaRsp, rsp, packet_id)
            return

        # 所有 reward_pool_id
        reward_pool_ids = [
            i["free_gacha_pool_i_d"] for i in pool["items"]
        ]

        # 抽卡
        for idx in range(draw_times):
            reward_pool_id = random.choice(reward_pool_ids)
            reward_pool = get_reward_pool(reward_pool_id)
            if not reward_pool or not reward_pool["items"]:
                continue

            reward = random.choice(reward_pool["items"])
            item_id = reward["item_i_d"]

            item = rsp.items.add()
            item.main_item.item_id = item_id
            item.main_item.item_tag = 7
            item.main_item.temp_pack_index = idx
            item.main_item.is_new = True  # 先全当新
            item.main_item.character.character_id = item_id

            item.extra_quality = calc_extra_quality(item_id)

        # 抽卡信息
        rsp.info.gacha_id = req.gacha_id
        rsp.info.gacha_times = draw_times
        rsp.info.has_full_pick = False
        rsp.info.is_free = False
        rsp.info.optional_up_item = 0
        rsp.info.optional_value = 0
        rsp.info.guarantee = 0

        session.send(MsgId.GachaRsp, rsp, packet_id)

        notice = Pack_pb2.PackNotice()
        notice.status = 1
        notice.temp_pack_max_size = 100
        notice.is_clear_temp_pack = False

        for it in rsp.items:
            # 假设：每抽到一个角色，给 10 个碎片
            pack_item = notice.items.add()
            pack_item.main_item.item_id = it.main_item.item_id + 100000  # 假设碎片ID
            pack_item.main_item.base_item.num = 10

        session.send(MsgId.PackNotice, notice, 0)
