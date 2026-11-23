from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbilityBadgeListReq,
    AbilityBadgeListRsp,
    Achieve,
    StatusCode,
)

import utils.db as db
from utils import achieve_track
from utils.res_loader import res


def _badge_scene_ids():
    """拥有星云树的场景(与官方一致: 其它场景不返回 ability_badge_pages)"""
    datas = res.get("MoonStone", {}).get("stone_area_data", {}).get("datas")
    if not isinstance(datas, (list, tuple)):
        return set()
    return {e.get("scene_i_d") for e in datas}


def _badge_achieve_ids():
    """星符成就 id 集合(stone_reward_quest_data.achieve_condition_i_d)"""
    datas = res.get("MoonStone", {}).get("stone_reward_quest_data", {}).get("datas")
    if not isinstance(datas, (list, tuple)):
        return set()
    return {
        info.get("achieve_condition_i_d")
        for entry in datas
        for info in entry.get("stone_reward_quest_data_group_info") or ()
    }


@packet_handler(MsgId.AbilityBadgeListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbilityBadgeListReq()
        req.ParseFromString(data)

        rsp = AbilityBadgeListRsp()
        rsp.status = StatusCode.StatusCode_OK

        achieve_track.sync_scoped_progress(session, _badge_achieve_ids())
        scenes = _badge_scene_ids()
        if req.scene_id:
            if req.scene_id in scenes:
                page = rsp.ability_badge_pages.add()
                page.page = req.scene_id
                page.active_box_ids.extend(
                    db.get_ability_tree(session.player_id, req.scene_id)
                )
        else:
            for k, v in db.get_ability_tree(session.player_id).items():
                page = rsp.ability_badge_pages.add()
                page.page = k
                page.active_box_ids.extend(v)

        # 树节点的解锁前置也必须回放，包含零进度；新号包有50001000/50001001。
        unlock_achieves = {
            aid
            for row in res["MoonStone"]["stone_unlock_data"]["datas"]
            for entry in row.get("stone_unlock_data_group_info") or ()
            for aid in entry.get("unlock_achieve_i_d") or ()
        }
        for a_id in sorted(_badge_achieve_ids() | unlock_achieves):
            blob = db.get_achieve(session.player_id, a_id)
            if not blob:
                continue
            achieve = Achieve()
            achieve.ParseFromString(blob)
            if achieve.count > 0 or a_id in unlock_achieves:
                rsp.ability_badge_achieves.add().CopyFrom(achieve)

        # 已领取星符奖励的成就 id(claimed_rewards 同存储)
        rsp.ability_badge_reward_achieve_ids.extend(
            int(k) for k in db.get_claimed(session.player_id, "badge_achieve")
        )
        session.send(MsgId.AbilityBadgeListRsp, rsp, packet_id)  # 1631,1632
