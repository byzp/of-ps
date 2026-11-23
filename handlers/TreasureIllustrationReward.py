from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TreasureIllustrationRewardReq,
    TreasureIllustrationRewardRsp,
    EArchaeologyType,
    StatusCode,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils.reward_resolver import resolve_reward
from utils import item_mgr, achieve_track

"""
# 考古图鉴领奖 4525 4526
# 各类图鉴条目的登记奖励在对应表的 collection_i_d(-> Reward.json):
#   Book.json book / Treasure.json treasure / Utensil.json utensil /
#   Furniture.json furniture / Shovel.json shovel
领取状态持久化在 claimed_rewards 表(system='treasure_illustration'),
key 格式为 '{archaeology_type}:{entry_id}', db.try_claim 原子去重
"""


def _has_dig_record(player_id):
    """是否存在 TreasureDig 写入的实际产出物记录。"""
    return any(
        (value or 0) > 0 for value in db.get_kv_ns(player_id, "archaeology").values()
    )


def get_collection_reward_id(archaeology_type, entry_id):
    """按图鉴类型与条目 id(兼容表内 i_d 或 item_i_d)查 collection_i_d"""
    table = Config.TREASURE_ILLUSTRATION_REWARD_TYPE_TABLES.get(archaeology_type)
    if not table:
        return 0
    for e in res.get(table[0], {}).get(table[1], {}).get("datas", ()):
        if e.get("i_d") == entry_id or e.get("item_i_d") == entry_id:
            return e.get("collection_i_d", 0)
    return 0


def _claim_key(archaeology_type, entry_id):
    """构建 claimed_rewards 的 key: '{archaeology_type}:{entry_id}'"""
    return f"{archaeology_type}:{entry_id}"


def get_rewarded_ids(player_id, archaeology_type):
    """返回该玩家某图鉴类型下已领取奖励的 entry_id 列表"""
    prefix = f"{archaeology_type}:"
    return [
        int(k[len(prefix) :])
        for k in db.get_claimed(player_id, "treasure_illustration")
        if k.startswith(prefix)
    ]


@packet_handler(MsgId.TreasureIllustrationRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureIllustrationRewardReq()
        req.ParseFromString(data)

        rsp = TreasureIllustrationRewardRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.archaeology_type = req.archaeology_type
        rsp.id = req.id

        reward_id = get_collection_reward_id(req.archaeology_type, req.id)
        if not reward_id:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(
                MsgId.TreasureIllustrationRewardRsp, rsp, packet_id
            )  # 4525,4526
            return

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        # 校验收集进度: 玩家需有任意考古挖掘记录(TreasureDig 写入 kv ns=archaeology)
        if not _has_dig_record(session.player_id):
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(
                MsgId.TreasureIllustrationRewardRsp, rsp, packet_id
            )  # 4525,4526
            return
        # 原子去重(claimed_rewards 表持久化); 资格校验失败不能消耗领取资格。
        if not db.try_claim(
            session.player_id,
            "treasure_illustration",
            _claim_key(req.archaeology_type, req.id),
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(
                MsgId.TreasureIllustrationRewardRsp, rsp, packet_id
            )  # 4525,4526
            return
        player_level = db.get_players_info(session.player_id, "level")[0]
        items = resolve_reward(reward_id, player_level)
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                items,
                rsp_items=rsp.rewards,
                pack_notice=pack,
                session=session,
            )
            # 每个图鉴条目只允许成功领奖一次，故此事件天然是“收集一种”。
            achieve_track.report(
                session,
                "archaeology_collect",
                archaeology_type=req.archaeology_type,
            )

        session.send(MsgId.TreasureIllustrationRewardRsp, rsp, packet_id)  # 4525,4526
        session.send(MsgId.PackNotice, pack, 0)
