"""achieve/任务组 handler 共用的发奖辅助。

奖励内容一律由调用方从资源表解析成 [(item_id, num), ...] 传入
(reward_i_d 类字段用 utils.reward_resolver.resolve_reward 解析),
本模块只负责入库与 PackNotice 推送。

物品收支统一走 utils/items.py 的 per-player lock,
不再持有独立的全局锁。
"""

from network.msg_id import MsgId
from proto.net_pb2 import PackNotice, StatusCode

import utils.db as db
from utils import item_mgr


def get_player_level(player_id):
    """读取玩家等级(players.level), 供 resolve_reward 按等级过滤奖池; 失败返回 0"""
    row = db.get_players_info(player_id, "level")
    return row[0] if row else 0


def grant_items(session, reward_list, rsp_items=None):
    """发放 [(item_id, num), ...] 并推送 PackNotice。

    rsp_items 传入 Rsp 里的 repeated ItemDetail 时, 每条填入
    num 为本次获得数量的 ItemDetail;
    PackNotice 里则是叠加后的背包总量。
    仅适用于可堆叠物品(货币/材料/徽章等), 武器防具等实例类物品不要走这里。
    """
    if not reward_list:
        return
    item_mgr.grant_items(
        session.player_id,
        reward_list,
        rsp_items=rsp_items,
        session=session,
    )
