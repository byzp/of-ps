from config import Config
import logging
import pickle
import random
import time
import threading
from threading import Lock

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivitySandbagHitReq,
    ActivitySandbagHitRsp,
    ActivitySandbagDropNotice,
    StatusCode,
)
import utils.db as db
from utils import achieve_track, refresh
from utils.res_loader import res

"""
# 打沙袋: 上报打击 4503 4504 -> 掉落宝箱通知 4508
配置来源 InteractionActivity.json activity_interaction(表内仅 i_d=10001, object_i_d=10301):
activity_interaction_item: {index, reward_pool_group_i_d 宝箱奖池(Reward.reward_pool),
output_ceiling 产出上限, reset_type 1=每日重置(缺省不重置), special_type}
每次打击最多掉 1 个宝箱, 从未达上限的池里随机; 宝箱经 ActivitySandbagReward 领取
"""

# 打沙袋内存态(与 ActivitySandbagReward 共享)
# 持久化于 kv(player_id=0, ns=sandbag), 懒加载 + 周期快照

sandbag_state = {}
lock_sandbag = Lock()
_sb_loaded = [False]
_sb_thread = [None]
logger = logging.getLogger(__name__)


def sb_load():
    if _sb_loaded[0]:
        return
    raw = db.get_kv(0, "sandbag", "snapshot", b"")
    if raw:
        data = pickle.loads(raw)
        for pid, st in data.items():
            st["server_claimed"] = set(st.get("server_claimed", ()))
            sandbag_state[pid] = st
    _sb_loaded[0] = True

    if _sb_thread[0] is None or not _sb_thread[0].is_alive():
        def _loop():
            while True:
                time.sleep(5)
                if db.db is None:
                    return
                with lock_sandbag:
                    snapshot = pickle.dumps(
                        {
                            pid: {
                                **st,
                                "server_claimed": list(st["server_claimed"]),
                            }
                            for pid, st in sandbag_state.items()
                        }
                    )
                try:
                    db.set_kv(0, "sandbag", "snapshot", snapshot)
                except AttributeError:
                    return
                except Exception:
                    logger.exception("sandbag autosave failed")

        _sb_thread[0] = threading.Thread(target=_loop, daemon=True, name="sandbag-autosave")
        _sb_thread[0].start()


def sb_save():
    pass  # 由周期线程统一保存


def interaction_cfg(activity_id):
    """activity_interaction 行; 活动 id 不匹配时容错取表内第一条(表内仅一条)"""
    rows = res["InteractionActivity"]["activity_interaction"]["datas"]
    for row in rows:
        if row.get("i_d") == activity_id:
            return row
    if rows:
        return rows[0]
    return None


def player_state(player_id):
    """取(必要时创建)玩家沙袋内存态并处理每日重置; 须在 lock_sandbag 内调用"""
    sb_load()
    day = str(refresh.day_index())
    st = sandbag_state.get(player_id)
    if st is None:
        st = {
            "day": day,
            "daily_drops": {},
            "life_drops": {},
            "boxes": [],
            "next_seq": 1,
            "server_claimed": set(),
        }
        sandbag_state[player_id] = st
    elif st["day"] != day:
        st["day"] = day
        st["daily_drops"] = {}  # reset_type=1 的池每日重置
    return st


@packet_handler(MsgId.ActivitySandbagHitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivitySandbagHitReq()
        req.ParseFromString(data)

        rsp = ActivitySandbagHitRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.activity_id = req.activity_id
        rsp.npc_id = req.npc_id
        rsp.hit_count = req.hit_count

        cfg = interaction_cfg(req.activity_id)
        items = cfg.get("activity_interaction_item", ()) if cfg else ()
        hits = (
            min(req.hit_count, Config.SANDBAG_MAX_HIT_PER_REQUEST)
            if req.hit_count > 0
            else 0
        )

        new_boxes = []
        if items:
            now = int(time.time())
            with lock_sandbag:
                st = player_state(session.player_id)
                for _ in range(hits):
                    avail = []
                    for it in items:
                        idx = it.get("index", 0)
                        ceiling = it.get("output_ceiling", 0)
                        drops = (
                            st["daily_drops"]
                            if it.get("reset_type", 0) == 1
                            else st["life_drops"]
                        )
                        if drops.get(idx, 0) < ceiling:
                            avail.append((it, drops))
                    if not avail:
                        break  # 全部池达产出上限
                    it, drops = random.choice(avail)
                    idx = it.get("index", 0)
                    drops[idx] = drops.get(idx, 0) + 1
                    box = {
                        "seq": st["next_seq"],
                        "pool_id": it.get("reward_pool_group_i_d", 0),
                        "create_time": now,
                        "used": False,
                    }
                    st["next_seq"] += 1
                    st["boxes"].append(box)
                    new_boxes.append(box)

        session.send(MsgId.ActivitySandbagHitRsp, rsp, packet_id)  # 4503,4504

        # 成就按成功处理的攻击次数计数，而不是按掉落宝箱数计数。每日首击
        # 使用带日期的持久化领取键去重，避免重试请求重复推进184。
        object_id = cfg.get("object_i_d") if cfg else 0
        if object_id and req.npc_id == object_id and hits:
            first_today = db.try_claim(
                session.player_id,
                "ach_sandbag_day",
                f"{cfg.get('i_d', req.activity_id)}:{refresh.day_index()}",
            )
            with achieve_track.batch(session):
                achieve_track.report(
                    session, "sandbag_hit", match=req.npc_id, amount=hits
                )
                if first_today:
                    achieve_track.report(session, "sandbag_day", match=req.npc_id)

        if new_boxes:
            notice = ActivitySandbagDropNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.activity_id = req.activity_id
            for box in new_boxes:
                b = notice.box_list.add()
                b.seq = box["seq"]
                b.pool_id = box["pool_id"]
                b.create_time = box["create_time"]
                b.use_status = False
            session.send(MsgId.ActivitySandbagDropNotice, notice, 0)  # 4508
