from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbilityBadgePageRewardReq,
    AbilityBadgePageRewardRsp,
    StatusCode,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res

"""
# 星云树(星符页)核心奖励 1635 1636
页配置(已对表验证): MoonStone.stone_area_data{i_d, scene_i_d, item_i_d,
reward_text_i_d}, req.page 对应 scene_i_d(AbilityBadgeList 也按 scene 分页)。
奖励内容: stone_area_data.reward_text_i_d(1001-1005/1051-1053) 在
String_*.string_moon_stone_text 中均为「核心奖励 ★十连抽 获得[限定券]x10」,
限定券即 Item 110(string_item_text 110), 故发放 110 x10。
领取状态持久化在 claimed_rewards 表(system='badge_page'), db.try_claim 原子去重。
页完成度由客户端入口判断；服务端保存节点激活记录并对领奖原子去重。
"""


@packet_handler(MsgId.AbilityBadgePageRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbilityBadgePageRewardReq()
        req.ParseFromString(data)

        rsp = AbilityBadgePageRewardRsp()
        rsp.page = req.page

        # 校验页存在: stone_area_data.scene_i_d == req.page
        found = False
        for area in res["MoonStone"]["stone_area_data"]["datas"]:
            if area.get("scene_i_d") == req.page:
                found = True
                break
        if not found:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.AbilityBadgePageRewardRsp, rsp, packet_id)
            return

        # 原子去重(claimed_rewards 表持久化)
        if not db.try_claim(session.player_id, "badge_page", req.page):
            rsp.status = StatusCode.StatusCode_ABILITY_BADGE_PAGE_REWARDED
            session.send(MsgId.AbilityBadgePageRewardRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        item_mgr.grant_items(
            session.player_id,
            [(110, 10)],
            rsp_items=rsp.items,
            session=session,
        )

        session.send(MsgId.AbilityBadgePageRewardRsp, rsp, packet_id)  # 1635,1636
