import random
import time

from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import GatherReq, GatherRsp, PackNotice, StatusCode
import utils.db as db
from utils import achieve_track, item_mgr, refresh
from utils.pb_create import make_Achieve
from utils.res_loader import res


def _rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def _scene_rows():
    section = res.get("ScenesConfigAsset", {}).get("Scenes", ())
    rows = section.get("datas", ()) if isinstance(section, dict) else section
    return rows if isinstance(rows, (list, tuple)) else ()


def _resolve_point(session, index, reward_id):
    """索引和奖励必须同时属于服务端当前场景的真实采集点。"""
    item_mgr.validate_counter(index, allow_zero=False, label="gather point index")
    scene = next(
        (row for row in _scene_rows() if row.get("ID") == session.scene_id),
        None,
    )
    if scene is None:
        raise item_mgr.EconomyConfigError("missing gather scene config")
    gather_id = None
    for group in scene.get("GatherPointSetInfo") or ():
        for point in group.get("GatherPointSets") or ():
            for pointer in point.get("LifeGatherPointers") or ():
                if pointer.get("Index") == index:
                    gather_id = pointer.get("GatherID")
                    break
            if gather_id is not None:
                break
        if gather_id is not None:
            break
    if gather_id is None:
        raise item_mgr.EconomyConfigError("gather point is not in current scene")
    group = next((row for row in _rows("Gather", "gather") if row.get("i_d") == gather_id), None)
    if group is None:
        raise item_mgr.EconomyConfigError("missing gather group config")
    info = next(
        (
            row
            for row in group.get("gather_group_info", ())
            if row.get("reward") == reward_id
        ),
        None,
    )
    if info is None:
        raise item_mgr.EconomyConfigError("gather reward does not belong to point")
    return group, info


@packet_handler(MsgId.GatherReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GatherReq()
        req.ParseFromString(data)
        rsp = GatherRsp()
        try:
            group, info = _resolve_point(
                session, req.gather_item.index, req.gather_item.reward
            )
            reward = next(
                (
                    row
                    for row in _rows("Gather", "gather_reward")
                    if row.get("i_d") == info["reward"]
                ),
                None,
            )
            choices = list(reward.get("gather_reward_group_info", ())) if reward else []
            normal = [choice for choice in choices if not choice.get("lucky")]
            lucky = [choice for choice in choices if choice.get("lucky")]
            if not normal:
                raise item_mgr.EconomyConfigError("missing normal gather reward")
            for choice in choices:
                item_mgr.validate_count(choice.get("count", 1), label="gather reward count")
                item_mgr.validate_item_id(choice.get("item_i_d"))
            gtype = int(info.get("new_weapon_type", 0))
            item_mgr.validate_counter(gtype, label="gather type")
            column = {
                4: "butterfly_num",
                5: "water_num",
                6: "pick_num",
                7: "wood_num",
                8: "stone_num",
                15: "stone_num",
            }.get(gtype)
            if column is None:
                raise item_mgr.EconomyConfigError("unsupported gather type")
            rules = _rows("Gather", "gather_rule")
            if not rules:
                raise item_mgr.EconomyConfigError("missing gather rule")
            limit = item_mgr.validate_counter(
                int(rules[0].get(column, 0) or 0),
                allow_zero=True,
                label="gather limit",
            )
            if not 0 <= Config.GATHER_LUCKY_CHANCE <= 1:
                raise item_mgr.EconomyConfigError("invalid gather lucky chance")
            item_mgr.validate_count(
                Config.GATHER_POINT_REFRESH_SECONDS, label="gather cooldown"
            )
            item_mgr.validate_counter(group["i_d"], label="gather group id")
        except (item_mgr.EconomyConfigError, KeyError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GatherRsp, rsp, packet_id)
            return

        daily_key = f"{column}:{refresh.day_index()}"
        point_key = f"{session.scene_id}:{session.channel_id}:{req.gather_item.index}"
        now = int(time.time())
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with (
            item_mgr.player_lock(session.player_id),
            item_mgr.deferred_notifications(),
            db.transaction(),
        ):
            cooldown = item_mgr.validate_counter(
                int(db.get_kv(session.player_id, "gather_points", point_key, 0) or 0),
                label="gather cooldown",
            )
            count = item_mgr.validate_counter(
                int(db.get_kv(session.player_id, "gather_daily", daily_key, 0) or 0),
                label="gather daily count",
            )
            if cooldown > now:
                rsp.status = StatusCode.StatusCode_GATHER_LIMIT
            elif limit and count >= limit:
                rsp.status = StatusCode.StatusCode_GATHER_LIMIT
            else:
                # is_lucky 仅由服务端随机结果决定, 客户端标志不参与选择。
                use_lucky = bool(lucky) and random.random() < Config.GATHER_LUCKY_CHANCE
                choice = random.choice(lucky if use_lucky else normal)
                item_mgr.grant_items(
                    session.player_id,
                    [(choice["item_i_d"], int(choice.get("count", 1)))],
                    rsp_items=rsp.items,
                    pack_notice=pack,
                    session=session,
                )
                new_count = item_mgr.checked_add(
                    count, 1, limit=Config.ECONOMY_UINT32_MAX
                )
                db.set_kv(session.player_id, "gather_daily", daily_key, new_count)
                db.set_kv(
                    session.player_id,
                    "gather_points",
                    point_key,
                    item_mgr.checked_add(
                        now,
                        Config.GATHER_POINT_REFRESH_SECONDS,
                        limit=Config.ECONOMY_UINT32_MAX,
                    ),
                )
                rsp.status = StatusCode.StatusCode_OK
                rsp.group_gather_limit.gather_group_id = group["i_d"]
                rsp.group_gather_limit.gather_limit.gather_type = gtype
                rsp.group_gather_limit.gather_limit.gather_num = new_count
                rsp.group_gather_limit.gather_limit.gather_limit_num = max(limit, 1)
                rsp.scene_gather_limit.scene_id = session.scene_id
                rsp.scene_gather_limit.gather_limits.add().CopyFrom(
                    rsp.group_gather_limit.gather_limit
                )
        rsp.index = req.gather_item.index
        rsp.item_level = 1
        session.send(MsgId.GatherRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        for item in rsp.items:
            make_Achieve(session, item.main_item.item_id)
            achieve_track.report(
                session,
                "gather",
                match=item.main_item.item_id,
                amount=item.main_item.base_item.num,
                wt=gtype,
            )
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
