import logging
import threading
import time

from config import Config
from proto.net_pb2 import (
    ChatChannelType,
    PackNotice,
    PlayerOfflineReason,
    PlayerOfflineRsp,
    PlayerSceneSyncDataNotice,
    SceneActionType,
    SceneWeatherChangeNotice,
    ServerSceneSyncDataNotice,
    StatusCode,
)
from network.msg_id import MsgId
from network.remote_link import rsend
from server.scene_data import (
    _action as action,
    _chat_msg as chat_msg,
    _rec_list as rec_list,
    _scene as scene,
    _scene_action as scene_action,
    _session_list as session_list,
    lock_action,
    lock_chat_msg,
    lock_rec_list,
    lock_scene,
    lock_scene_action,
    lock_session,
    save_session_location,
    up_scene_action,
)
import utils.db as db
from utils import item_mgr as items_util, mail_rewards, weather
from utils.res_loader import res

logger = logging.getLogger(__name__)

max_tps = Config.SERVER_MAX_TPS
game_time_seconds = float(Config.INITIAL_GAME_TIME_SECONDS)
tod_time = game_time_seconds
_rel_time = 0.0
_last_send_time = 0.0
_last_stamina_sync_time = 0

SPEED_MULTIPLIER = 86400.0 / weather.config_int(
    "Tod_Diurnal_Cycle", Config.GAME_DAY_REAL_SECONDS
)
SEND_INTERVAL_REAL = Config.SCENE_STATE_SYNC_INTERVAL
STAMINA_INTERVAL = Config.STAMINA_SYNC_INTERVAL

_lifecycle_lock = threading.Lock()
_stop_event = threading.Event()
_stopped_event = threading.Event()
_stamina_requested = threading.Event()
_thread = None
_stamina_thread = None
_failed = False
sync_stop = False


def set_time_of_day(seconds):
    """设置当前游戏日时间，与同步循环共用时钟和锁；86400表示次日零点。"""
    global game_time_seconds, tod_time, _rel_time, _last_send_time
    with lock_session:
        previous_weather = weather.weather_at(int(game_time_seconds // 3600))
        game_time_seconds = (game_time_seconds // 86400) * 86400 + seconds
        tod_time = game_time_seconds % 86400.0
        _rel_time = time.time()
        _last_send_time = 0.0
        current_weather = weather.weather_at(int(game_time_seconds // 3600))
        if previous_weather != current_weather:
            notice = SceneWeatherChangeNotice(
                status=StatusCode.StatusCode_OK, weather_type=current_weather
            )
            for session in session_list:
                if session.logged_in:
                    session.send(MsgId.SceneWeatherChangeNotice, notice, 0)


def init():
    global _rel_time, _last_stamina_sync_time, _thread, _stamina_thread, _failed, sync_stop
    with _lifecycle_lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        _stop_event.clear()
        _stopped_event.clear()
        _stamina_requested.clear()
        sync_stop = False
        _failed = False
        _rel_time = time.time()
        _last_stamina_sync_time = _rel_time
        _stamina_thread = threading.Thread(
            target=_stamina_loop, daemon=False, name="notice-stamina"
        )
        _thread = threading.Thread(target=start_loop, daemon=False, name="notice-sync")
        _stamina_thread.start()
        _thread.start()
        return _thread


def _dispatch_action(scene_id, channel_id, notice):
    """发送一个场景频道内的动作，并转发给对端服务器。"""
    if notice.from_player_id < 1010000:
        rsend(MsgId.SendActionNotice, notice, [scene_id, channel_id])
    for session in get_scene_sessions(scene_id, channel_id):
        session.send(MsgId.SendActionNotice, notice, 0)


def start_loop():
    global _failed, sync_stop
    try:
        notice_sync_loop()
    except Exception:
        # A background thread must never bypass the main shutdown/save path.
        logger.exception("A fatal error occurred in notice_sync_loop")
        with _lifecycle_lock:
            _failed = True
            sync_stop = True
            _stop_event.set()
            _stamina_requested.set()
    finally:
        _stopped_event.set()


def failed():
    with _lifecycle_lock:
        return _failed


def stop():
    """Wake both loops, wait for stamina writes, then wait for the final save."""
    with _lifecycle_lock:
        global sync_stop
        sync_stop = True
        _stop_event.set()
        _stamina_requested.set()
        stamina_thread = _stamina_thread
        thread = _thread

    if stamina_thread is not None and stamina_thread is not threading.current_thread():
        stamina_thread.join()
    if thread is not None and thread is not threading.current_thread():
        thread.join()
    _stopped_event.set()


def wait_stopped(timeout=None):
    return _stopped_event.wait(timeout)


def _is_local(session):
    return not getattr(session, "remote", False)


def _save_local_session(session, timestamp):
    if not _is_local(session) or not getattr(session, "logged_in", False):
        return
    try:
        save_session_location(session, force=True)
    except Exception:
        logger.exception("Unable to save location for player %s", session.player_id)
    try:
        db.set_players_info(session.player_id, "last_login_time", int(timestamp * 1000))
    except Exception:
        logger.exception("Unable to save logout time for player %s", session.player_id)


def _cleanup_disconnected_locked(timestamp):
    for session in list(session_list):
        if getattr(session, "running", False) or not getattr(session, "logged_in", False):
            continue
        if _is_local(session):
            try:
                mail_rewards.recover_drops(session)
            except Exception:
                logger.exception("Unable to recover drops for player %s", session.player_id)
        _save_local_session(session, timestamp)
        logger.info("Player logout: %s(%s)", session.player_name, session.player_id)

        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        data = notice.data.add()
        data.player_id = session.player_id
        server_data = data.server_data.add()
        server_data.action_type = SceneActionType.SceneActionType_LEAVE
        up_scene_action(session.scene_id, session.channel_id, notice)
        session.logged_in = False

    session_list[:] = [session for session in session_list if getattr(session, "running", False)]


def _shutdown_sessions_locked(timestamp):
    logger.info("Save player data...")
    response = PlayerOfflineRsp()
    response.status = StatusCode.StatusCode_OK
    response.reason = PlayerOfflineReason.PlayerOfflineReason_SERVER_SHUTDOWN
    for session in list(session_list):
        if getattr(session, "running", False) and getattr(session, "logged_in", False):
            try:
                session.send(MsgId.PlayerOfflineRsp, response, 0)
            except Exception:
                logger.exception("Unable to send offline notice")
    for session in list(session_list):
        _save_local_session(session, timestamp)
        session.logged_in = False
    # A same-process restart must not inherit remote or local session objects.
    session_list.clear()


def notice_sync_loop():
    global tod_time, game_time_seconds, _rel_time, _last_send_time, _last_stamina_sync_time
    while not _stop_event.is_set() and not sync_stop:
        start_t = time.time()

        # 只在维护会话列表和读取时钟时持有会话锁。广播和数据库操作都使用快照，
        # 这样动作 worker 可以同时获取其他场景的会话。
        with lock_session:
            if _stop_event.is_set() or sync_stop:
                _shutdown_sessions_locked(start_t)
                return

            _cleanup_disconnected_locked(start_t)
            elapsed_real = start_t - _rel_time
            if elapsed_real > 0:
                previous_weather = weather.weather_at(int(game_time_seconds // 3600))
                game_time_seconds += elapsed_real * SPEED_MULTIPLIER
                tod_time = game_time_seconds % 86400.0
                _rel_time = start_t
                current_weather = weather.weather_at(int(game_time_seconds // 3600))
                if previous_weather != current_weather:
                    notice = SceneWeatherChangeNotice(
                        status=StatusCode.StatusCode_OK, weather_type=current_weather
                    )
                    for session in session_list:
                        if session.logged_in:
                            session.send(MsgId.SceneWeatherChangeNotice, notice, 0)
            with lock_action:
                # 1970 玩家动作广播
                for scene_id, channel_id, action_notice in action:
                    if action_notice.from_player_id < 1010000:
                        rsend(MsgId.SendActionNotice, action_notice, [scene_id, channel_id])
                    for session in session_list:
                        if session.scene_id == scene_id and session.channel_id == channel_id:
                            session.send(MsgId.SendActionNotice, action_notice, 0)
                action.clear()
            with lock_scene_action:
                if start_t - _last_send_time >= SEND_INTERVAL_REAL:
                    time_sync = True
                    _last_send_time = start_t
                else:
                    time_sync = False
                for session in session_list:
                    # 1208 场景时间同步
                    if time_sync:
                        response = ServerSceneSyncDataNotice()
                        response.status = StatusCode.StatusCode_OK
                        tmp = response.data.add().server_data.add()
                        tmp.action_type = SceneActionType.SceneActionType_TOD_UPDATE
                        tmp.tod_time = int(tod_time)
                        session.send(MsgId.ServerSceneSyncDataNotice, response, 0)
                    # 1208 其他事件
                    for notice in scene_action[session.scene_id][session.channel_id]:
                        session.send(MsgId.ServerSceneSyncDataNotice, notice, 0)
                for scene_id, scene_t in scene_action.items():
                    for channel_id, channel in scene_t.items():
                        for notice in channel:
                            for data in notice.data:
                                if data.player_id < 1010000:
                                    rsend(
                                        MsgId.ServerSceneSyncDataNotice,
                                        notice,
                                        [scene_id, channel_id],
                                    )
                scene_action.clear()
            with lock_chat_msg:
                for session in session_list:
                    # 聊天信息同步
                    for msg in chat_msg:
                        if msg[3].msg.player_id == session.player_id:
                            continue
                        match msg[3].type:
                            case ChatChannelType.ChatChannel_Default:
                                if session.scene_id == msg[1] and session.channel_id == msg[2]:
                                    session.send(MsgId.ChatMsgNotice, msg[3], 0)
                            case ChatChannelType.ChatChannel_ChatRoom:
                                if session.chat_channel_id == msg[0]:
                                    session.send(MsgId.ChatMsgNotice, msg[3], 0)
                for msg in chat_msg:
                    if msg[3].msg.player_id < 1010000:
                        rsend(MsgId.ChatMsgNotice, msg[3], [msg[0], msg[1], msg[2]])
                chat_msg.clear()
            with lock_scene:
                with lock_rec_list:
                    # 1206 玩家动作同步
                    for scene_id, channel_id in rec_list:
                        response = PlayerSceneSyncDataNotice()
                        response.status = StatusCode.StatusCode_OK
                        other_notice = []
                        for player_id, value in scene[scene_id][channel_id].items():
                            if player_id < 1010000:
                                tmp = response.data.add()
                                tmp.player_id = player_id
                                tmp.data.add().CopyFrom(value)
                            else:
                                other_notice.append((player_id, value))
                        rsend(1206, response, [scene_id, channel_id])
                        for player_id, value in other_notice:
                            tmp = response.data.add()
                            tmp.player_id = player_id
                            tmp.data.add().CopyFrom(value)
                        scene[scene_id][channel_id].clear()
                        for session in session_list:
                            if session.scene_id == scene_id and session.channel_id == channel_id:
                                session.send(MsgId.PlayerSceneSyncDataNotice, response, 0)
                    rec_list.clear()
            if start_t - _last_stamina_sync_time > STAMINA_INTERVAL:
                _stamina_requested.set()
                _last_stamina_sync_time = start_t
        use_time = time.time() - start_t
        wait_time = 1.0 / max_tps - use_time
        if use_time > 1:
            logger.debug("notice sync time: %s", use_time)
        if wait_time > 0:
            _stop_event.wait(wait_time)

    # stop() may arrive after the loop's top-of-cycle check.  Always pass
    # through the final save path before the notice thread is allowed to exit.
    with lock_session:
        _shutdown_sessions_locked(time.time())


def _stamina_loop():
    while not _stop_event.is_set():
        if not _stamina_requested.wait(0.5):
            continue
        _stamina_requested.clear()
        if _stop_event.is_set():
            break
        with lock_session:
            sessions = [
                session
                for session in session_list
                if _is_local(session)
                and getattr(session, "running", False)
                and getattr(session, "logged_in", False)
            ]
        try:
            _stamina_sync(sessions)
        except Exception:
            logger.exception("Stamina sync failed")


# 体力恢复节奏 = GlobalConfig.Player_Recover_Vitality_Second(600秒/点);
_vit_tick = False


def _stamina_caps(level):
    """按玩家等级查 Level.player_level 的体力/精力上限, 表缺失兜底 150/800"""
    for entry in res["Level"]["player_level"]["datas"]:
        if entry["i_d"] == level:
            return (
                entry.get("player_vitality", Config.VITALITY_MAX_FALLBACK),
                entry.get("player_energy", Config.ENERGY_MAX_FALLBACK),
            )
    return Config.VITALITY_MAX_FALLBACK, Config.ENERGY_MAX_FALLBACK


def _stamina_sync(sessions):
    global _vit_tick
    _vit_tick = not _vit_tick

    for session in sessions:
        if _stop_event.is_set():
            break
        if session.running and session.logged_in:
            row = db.get_players_info(session.player_id, "level")
            vit_cap, energy_cap = _stamina_caps(row[0] if row else 0)
            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            # 与领奖/扣费共用该玩家的物品读改写锁(按玩家粒度, 不影响其他玩家)
            with items_util.player_lock(session.player_id):
                for item_id, add, cap in (
                    (10, 1 if _vit_tick else 0, vit_cap),  # 体力
                    (11, 5, energy_cap),  # 精力
                ):
                    item_b = db.get_item_detail(session.player_id, item_id)
                    if not item_b:
                        continue  # 从未持有则不自然恢复
                    item = pack.items.add()
                    item.ParseFromString(item_b)
                    num = item.main_item.base_item.num
                    new_num = min(num + add, cap) if num < cap else num
                    if new_num != num:
                        item.main_item.base_item.num = new_num
                        db.set_item_detail(session.player_id, item.SerializeToString(), item_id)
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
