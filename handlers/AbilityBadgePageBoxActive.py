from utils import achieve_track

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbilityBadgePageBoxActiveReq,
    AbilityBadgePageBoxActiveRsp,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res
from utils import badge_tree, item_mgr

"""
# 能力徽章页格子激活 1633 1634(官方抓包 pack/pack6.0 实证)
包序: Rsp(status+page+box_id+items) → 1400(消耗与获得合并一份)。
page对应stone_area_data.scene_i_d，经unlock_i_d选择stone_unlock_data，
再按box_i_d查节点，消耗其item_i_d x item_count；行列号仅是布局。
节点奖励由badge_tree统一提供，使用通用物品发放同步功能与能力解锁。
"""


def _box_cfg(page, box_id):
    area = next(
        (
            row
            for row in res["MoonStone"]["stone_area_data"]["datas"]
            if row.get("scene_i_d") == page
        ),
        None,
    )
    if area is None:
        return None
    for row in res.get("MoonStone", {}).get("stone_unlock_data", {}).get("datas", ()):
        if row.get("i_d") != area.get("unlock_i_d"):
            continue
        for g in row.get("stone_unlock_data_group_info", ()):
            if g.get("box_i_d") == box_id:
                return g
    return None


@packet_handler(MsgId.AbilityBadgePageBoxActiveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with badge_tree.activation_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = AbilityBadgePageBoxActiveReq()
        req.ParseFromString(data)

        rsp = AbilityBadgePageBoxActiveRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.page = req.page
        rsp.box_id = req.box_id
        ids = db.get_ability_tree(session.player_id, req.page)
        if isinstance(ids, dict):
            ids = []
        if req.box_id in ids:
            # 重复激活: 幂等回显, 不再消耗
            session.send(MsgId.AbilityBadgePageBoxActiveRsp, rsp, packet_id)
            return

        box = _box_cfg(req.page, req.box_id)
        if box is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.AbilityBadgePageBoxActiveRsp, rsp, packet_id)
            return

        cost_item = int(box.get("item_i_d", 0) or 0)
        cost_num = int(box.get("item_count", 0) or 0)
        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            if cost_item and cost_num:
                if not item_mgr.consume_items(
                    session.player_id,
                    [(cost_item, cost_num)],
                    pack_notice=notice,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    session.send(MsgId.AbilityBadgePageBoxActiveRsp, rsp, packet_id)
                    return
            ids.append(req.box_id)
            db.set_ability_tree(session.player_id, req.page, ids)
            item_mgr.grant_items(
                session.player_id,
                badge_tree.rewards(req.page, req.box_id),
                rsp_items=rsp.items,
                pack_notice=notice,
                session=session,
            )
            if req.page == 1 and req.box_id == 31:
                # 成就44(通过星云树解锁二段跳)推进任务链
                achieve_track.report(session, "double_jump", match=101000000)
            session.send(MsgId.AbilityBadgePageBoxActiveRsp, rsp, packet_id)
            if len(notice.items):
                session.send(MsgId.PackNotice, notice, 0)
