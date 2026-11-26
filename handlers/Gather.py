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


@packet_handler(MsgId.GatherReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GatherReq()
        req.ParseFromString(data)
        rsp = GatherRsp()
        matched = None
        for group in _rows("Gather", "gather"):
            for info in group.get("gather_group_info", ()):
                if info.get("reward") == req.gather_item.reward:
                    matched = (group, info)
                    break
            if matched:
                break
        if not matched:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.GatherRsp, rsp, packet_id)
            return
        group, info = matched
        reward = next(
            (row for row in _rows("Gather", "gather_reward") if row.get("i_d") == info["reward"]),
            None,
        )
        choices = reward.get("gather_reward_group_info", ()) if reward else ()
        if not choices:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GatherRsp, rsp, packet_id)
            return
        try:
            for choice in choices:
                item_mgr.validate_count(choice.get("count", 1), label="gather reward count")
                item_mgr.validate_item_id(choice.get("item_i_d"))
            gtype = int(info.get("new_weapon_type", 0))
            column = {
                0: "wood_num", 1: "wood_num", 2: "flower_num", 3: "stone_num",
                4: "butterfly_num", 5: "water_num", 6: "pick_num",
            }.get(gtype, "wood_num")
            rules = _rows("Gather", "gather_rule")
            if not rules:
                raise item_mgr.EconomyConfigError("missing gather rule")
            limit = item_mgr.validate_counter(
                int(rules[0].get(column, 0) or 0), allow_zero=True, label="gather limit"
            )
            if not 0 <= Config.GATHER_LUCKY_CHANCE <= 1:
                raise item_mgr.EconomyConfigError("invalid gather lucky chance")
            item_mgr.validate_count(
                Config.GATHER_POINT_REFRESH_SECONDS, label="gather cooldown"
            )
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GatherRsp, rsp, packet_id)
            return

        daily_key = f"{column}:{refresh.day_index()}"
        point_key = f"{session.scene_id}:{session.channel_id}:{req.gather_item.index}"
        now = int(time.time())
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with item_mgr.player_lock(session.player_id), db.transaction():
            cooldown = int(db.get_kv(session.player_id, "gather_points", point_key, 0) or 0)
            count = item_mgr.validate_counter(
                int(db.get_kv(session.player_id, "gather_daily", daily_key, 0) or 0),
                label="gather daily count",
            )
            if cooldown > now:
                rsp.status = StatusCode.StatusCode_GATHER_LIMIT
            elif limit and count >= limit:
                rsp.status = StatusCode.StatusCode_GATHER_LIMIT
            else:
                choice = choices[1] if len(choices) > 1 and random.random() < Config.GATHER_LUCKY_CHANCE else choices[0]
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
                    now + Config.GATHER_POINT_REFRESH_SECONDS,
                )
                rsp.status = StatusCode.StatusCode_OK
                rsp.group_gather_limit.gather_group_id = group["i_d"]
                rsp.group_gather_limit.gather_limit.gather_type = gtype
                rsp.group_gather_limit.gather_limit.gather_num = new_count
                rsp.group_gather_limit.gather_limit.gather_limit_num = max(limit, 1)
                rsp.scene_gather_limit.scene_id = session.scene_id
                rsp.scene_gather_limit.gather_limits.add().CopyFrom(rsp.group_gather_limit.gather_limit)
        rsp.index = req.gather_item.index
        rsp.item_level = 1
        session.send(MsgId.GatherRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        for item in rsp.items:
            make_Achieve(session, item.main_item.item_id)
            achieve_track.report(session, "gather", match=item.main_item.item_id, amount=item.main_item.base_item.num, wt=gtype)
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
