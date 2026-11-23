from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TreasureIllustrationInfoReq,
    TreasureIllustrationInfoRsp,
    EArchaeologyType,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res


def _reward_pool_of(achieve_id):
    """ArchaeologyAchieve: achieve_i_d -> reward_i_d(Reward.reward_pool)"""
    for entry in res["ArchaeologyAchieve"]["archaeology_achieve"]["datas"]:
        for it in entry.get("items", ()):
            if it.get("achieve_i_d") == achieve_id:
                return it.get("reward_i_d")
    return None


"""
# 考古图鉴信息查询 4523 4524
# 返回各类图鉴(书籍/器物/宝藏/铲子)已领奖 id 与考古成就进度
# 已领取状态持久化于 claimed_rewards 表:
#   图鉴登记奖励 system='treasure_illustration', key='{type}:{entry_id}'
#   考古成就奖励 system='treasure_achieve', key=achieve_id
"""


def _rewarded_illustration_ids(player_id, archaeology_type):
    """从 claimed_rewards 表读取该图鉴类型下已领取的 entry_id"""
    prefix = f"{archaeology_type}:"
    return sorted(
        int(k[len(prefix) :])
        for k in db.get_claimed(player_id, "treasure_illustration")
        if k.startswith(prefix)
    )


@packet_handler(MsgId.TreasureIllustrationInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureIllustrationInfoReq()
        req.ParseFromString(data)

        rsp = TreasureIllustrationInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 各类图鉴已领取的登记奖励 id(持久化于 claimed_rewards)
        rsp.book_reward.extend(
            _rewarded_illustration_ids(
                session.player_id, EArchaeologyType.EArchaeologyType_Book
            )
        )
        rsp.treasure_reward.extend(
            _rewarded_illustration_ids(
                session.player_id, EArchaeologyType.EArchaeologyType_TreasureMap
            )
        )
        rsp.utensil_reward.extend(
            _rewarded_illustration_ids(
                session.player_id, EArchaeologyType.EArchaeologyType_Utensil
            )
        )
        rsp.shovel_reward.extend(
            _rewarded_illustration_ids(
                session.player_id, EArchaeologyType.EArchaeologyType_Shovel
            )
        )

        # 考古成就: ArchaeologyAchieve.json archaeology_achieve 按类型分组
        rewarded_achieves = set(
            int(k) for k in db.get_claimed(session.player_id, "treasure_achieve")
        )
        _named = {
            1: EArchaeologyType.EArchaeologyType_TreasureMap,
            2: EArchaeologyType.EArchaeologyType_Shovel,
            3: EArchaeologyType.EArchaeologyType_Furniture,
            4: EArchaeologyType.EArchaeologyType_Utensil,
        }
        by_type = {}
        for e in (
            res.get("ArchaeologyAchieve", {})
            .get("archaeology_achieve", {})
            .get("datas", ())
        ):
            for it in e.get("items", ()):
                aid = it.get("achieve_i_d")
                if not aid:
                    continue
                if aid % 100 == 1:
                    a_type = _named.get((aid // 100) % 10, 0)
                else:
                    a_type = 0
                by_type.setdefault(a_type, []).append(aid)
        for a_type in Config.TREASURE_ILLUSTRATION_INFO_ALL_TYPES:
            ta = rsp.achieves.add()
            ta.achieve_type = a_type
            for achieve_id in by_type.get(a_type, ()):
                a = ta.treasure_achieve_.add()
                a.achieve_id = achieve_id
                # 进度: 该成就对应奖励池的累计挖掘次数(kv ns=archaeology)
                reward_pool = _reward_pool_of(achieve_id)
                if reward_pool:
                    a.count = (
                        db.get_kv(
                            session.player_id,
                            "archaeology",
                            str(reward_pool),
                            0,
                        )
                        or 0
                    )
                if achieve_id in rewarded_achieves:
                    ta.rewarded_treasure_achieve_id_lst.append(achieve_id)

        session.send(MsgId.TreasureIllustrationInfoRsp, rsp, packet_id)  # 4523,4524
