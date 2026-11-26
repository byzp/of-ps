"""social 组共享内存态模块(照片分享墙 / 实物奖品收货地址 / 心愿单 / SP密码)。

本模块不含 Handler 类, 仅被 social 组 handler import。
状态通过 player_kv(player_id=0) 做整体快照持久化: 启动时 load(),
后台线程周期性脏检测保存, 重启不丢。
"""

import copy
import logging
import pickle
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PERSIST_KEY = ("photo_share", "snapshot")
_autosave_started = [False]
_last_snapshot = [None]

# ---------------- 照片分享墙 ----------------
photos = {}
lock_photo = threading.RLock()

_next_code = [int(time.time()) * 100]  # 分享码, 用时间戳做基数避免重启后重复


def new_photo_code():
    """分配一个新的照片分享码(调用方无需持锁)"""
    with lock_photo:
        _next_code[0] += 1
        return _next_code[0]


# 每人额外购买的上传格子数 {player_id: int}
extra_upload_grid = {}

# 上传上限基础值(未知, 暂定)
UPLOAD_MAX_BASE = 30
TODAY_UPLOAD_LIMIT = 10


def fill_preview(info, record, viewer_id):
    """用内存记录填充 PhotoPreviewInfo"""
    info.code = record["code"]
    info.player_label = record["player_id"]
    info.player_id = record["player_id"]
    info.player_name = record["player_name"]
    info.head = record["head"]
    info.title = record["title"]
    info.likes_total = len(record["likes"])
    info.likes_status = viewer_id in record["likes"]
    info.activity_id = record["activity_id"]
    info.status = 1  # AuditStatus_SUCCESS


def fill_detail(info, record, viewer_id):
    """用内存记录填充 PhotoDetailInfo"""
    info.code = record["code"]
    info.player_label = record["player_id"]
    info.player_id = record["player_id"]
    info.player_name = record["player_name"]
    info.head = record["head"]
    info.upload_time = record["upload_time"]
    info.title = record["title"]
    info.tag1 = record["tag1"]
    info.tag2 = record["tag2"]
    info.tag3 = record["tag3"]
    info.likes_total = len(record["likes"])
    info.favorite_total = len(record["favorites"])
    info.dye_download_total = record["dye_download_total"]
    info.likes_status = viewer_id in record["likes"]
    info.favorite_status = viewer_id in record["favorites"]
    info.character_id = record["character_id"]
    info.weapon_id = record["weapon_id"]
    info.activity_id = record["activity_id"]
    if record["camera_param"]:
        info.camera_param.ParseFromString(record["camera_param"])
    info.status = 1  # AuditStatus_SUCCESS


# ---------------- 实物奖品收货地址 ----------------
express_address = {}
lock_express = threading.Lock()

# ---------------- 心愿单 ----------------
wish_lists = {}
# 本周为好友赠送次数 {player_id: int} (自动保存线程每周一清零)
week_send_count = {}
lock_wish = threading.Lock()

WISH_LIST_MAX = 10  # 心愿单容量上限(未知, 暂定)


def find_wish_pool_id(shop_id, grid_id):
    """由商店格子反查奖池 id, 查不到返回 0"""
    try:
        from utils.res_loader import res

        for grid in res["Shop"]["grid"]["datas"]:
            if grid.get("i_d") == shop_id:
                for items in grid.get("items", []):
                    if items.get("grid_i_d") == grid_id:
                        return items.get("shop_pool_i_d", 0)
    except Exception:
        pass
    return 0


# ---------------- SP(二级密码) ----------------
# {player_id: {"password": str, "open": bool}}
sp_state = {}
lock_sp = threading.Lock()


# ---------------- 持久化(整体快照) ----------------


def _snapshot():
    with lock_photo, lock_express, lock_wish, lock_sp:
        return copy.deepcopy({
            "photos": photos,
            "extra_upload_grid": extra_upload_grid,
            "express_address": express_address,
            "wish_lists": wish_lists,
            "week_send_count": week_send_count,
            "sp_state": sp_state,
            "next_code": _next_code[0],
        })


def _restore(snap: dict):
    photos.update(snap.get("photos", {}))
    extra_upload_grid.update(snap.get("extra_upload_grid", {}))
    express_address.update(snap.get("express_address", {}))
    wish_lists.update(snap.get("wish_lists", {}))
    week_send_count.update(snap.get("week_send_count", {}))
    sp_state.update(snap.get("sp_state", {}))
    _next_code[0] = max(_next_code[0], snap.get("next_code", 0))


def load():
    """启动时从 player_kv 恢复快照(需在 db.init() 之后调用)"""
    import utils.db as db

    try:
        raw = db.get_kv(0, *_PERSIST_KEY)
        if raw:
            _restore(pickle.loads(raw))
            logger.info(
                "photo_share state restored: %d photos, %d wish lists",
                len(photos),
                len(wish_lists),
            )
    except Exception:
        logger.exception("photo_share load failed")
    photo_directory = Path("data/photos")
    if photo_directory.is_dir():
        for path in photo_directory.glob("*.bin"):
            try:
                code = int(path.stem)
            except ValueError:
                continue
            if code not in photos:
                path.unlink(missing_ok=True)
    _start_autosave()


def save():
    """整体快照写入 player_kv"""
    import utils.db as db

    try:
        snap = pickle.dumps(_snapshot())
        if snap != _last_snapshot[0]:
            db.set_kv(0, *_PERSIST_KEY, snap)
            _last_snapshot[0] = snap
    except Exception:
        logger.exception("photo_share save failed")


def _start_autosave():
    if _autosave_started[0]:
        return
    _autosave_started[0] = True

    def _loop():
        week = [time.strftime("%G-W%V")]
        while True:
            time.sleep(10)
            # 周重置: 好友赠送次数每周清零
            cur = time.strftime("%G-W%V")
            if cur != week[0]:
                week[0] = cur
                with lock_wish:
                    week_send_count.clear()
            save()

    threading.Thread(target=_loop, daemon=True, name="photo-share-autosave").start()
