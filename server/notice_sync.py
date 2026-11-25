import time
import threading
import logging
import os
import traceback

from config import Config
from proto.net_pb2 import (
    ServerSceneSyncDataNotice,
    StatusCode,
    PlayerOfflineRsp,
    PlayerOfflineReason,
    SceneActionType,
    ChatChannelType,
    PlayerSceneSyncDataNotice,
    PackNotice,
    SceneWeatherChangeNotice,
)
from network.msg_id import MsgId
from network.remote_link import rsend
from server.scene_data import (
    _chat_msg as chat_msg,
    lock_chat_msg,
    _scene_action as scene_action,
    lock_scene_action,
    _session_list as session_list,
    lock_session,
    _rec_list as rec_list,
    lock_rec_list,
    _scene as scene,
    lock_scene,
    get_scene_sessions,
    start_action_workers,
    stop_action_workers,
    up_scene_action,
)
import utils.db as db
from utils import weather, item_mgr as items_util, mail_rewards
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
    global _rel_time, _last_stamina_sync_time
    _rel_time = time.time()
    _last_stamina_sync_time = _rel_time
    start_action_workers(_dispatch_action, Config.ACTION_SYNC_WORKERS)
    threading.Thread(target=start_loop, daemon=False).start()


def _dispatch_action(scene_id, channel_id, notice):
    """发送一个场景频道内的动作，并转发给对端服务器。"""
    if notice.from_player_id < 1010000:
        rsend(MsgId.SendActionNotice, notice, [scene_id, channel_id])
    for session in get_scene_sessions(scene_id, channel_id):
        session.send(MsgId.SendActionNotice, notice, 0)


def start_loop():
    status_code = 0
    try:
        notice_sync_loop()
    except Exception as e:
        traceback.print_exc()
        logger.error("A fatal error occurred in notice_sync_loop! Clear and exit.")
        status_code = 1
    finally:
        stop_action_workers()
        db.exit()
        os._exit(status_code)


def notice_sync_loop():
    global tod_time, game_time_seconds, _rel_time, _last_send_time, _last_stamina_sync_time
    # 允许测试或嵌入式调用直接进入同步循环，和 init() 保持相同的启动语义。
    start_action_workers(_dispatch_action, Config.ACTION_SYNC_WORKERS)
    while True:
        start_t = time.time()

        # 只在维护会话列表和读取时钟时持有会话锁。广播和数据库操作都使用快照，
        # 这样动作 worker 可以同时获取其他场景的会话。
        with lock_session:
            stopping = sync_stop
            if stopping:
                shutdown_sessions = list(session_list)
                departed_sessions = []
                active_sessions = []
            else:
                departed_sessions = [
                    session
                    for session in session_list
                    if not session.running and session.logged_in
                ]
                session_list[:] = [
                    session
                    for session in session_list
                    if getattr(session, "running", False)
                ]
                active_sessions = list(session_list)

        if stopping:
            logger.info("Save player data...")
            # 先排空动作队列，避免正常关闭时丢失已经接收的动作。
            stop_action_workers(drain=True)
            rsp = PlayerOfflineRsp()
            rsp.status = StatusCode.StatusCode_OK
            rsp.reason = PlayerOfflineReason.PlayerOfflineReason_SERVER_SHUTDOWN
            for session in shutdown_sessions:
                if session.running and session.logged_in:
                    session.send(MsgId.PlayerOfflineRsp, rsp, 0)
            for session in shutdown_sessions:
                if session.logged_in:
                    db.set_players_info(
                        session.player_id, "last_login_time", int(start_t * 1000)
                    )
            return

        # 清理掉线玩家和产生离开事件，这些操作不再阻塞其他场景的广播。
        for session in departed_sessions:
            mail_rewards.recover_drops(session)
            db.set_players_info(
                session.player_id, "last_login_time", int(start_t * 1000)
            )
            logger.info(f"Player logout: {session.player_name}({session.player_id})")
            notice = ServerSceneSyncDataNotice()
            notice.status = StatusCode.StatusCode_OK
            d = notice.data.add()
            d.player_id = session.player_id
            sd = d.server_data.add()
            sd.action_type = SceneActionType.SceneActionType_LEAVE
            up_scene_action(session.scene_id, session.channel_id, notice)

        with lock_session:
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
            current_tod_time = int(tod_time)
        if elapsed_real > 0 and previous_weather != current_weather:
            for session in active_sessions:
                if session.logged_in:
                    session.send(MsgId.SceneWeatherChangeNotice, notice, 0)

        with lock_session:
            if start_t - _last_send_time >= SEND_INTERVAL_REAL:
                time_sync = True
                _last_send_time = start_t
            else:
                time_sync = False

        with lock_scene_action:
            pending_scene_actions = {
                (scene_id, channel_id): list(channel)
                for scene_id, scene_t in scene_action.items()
                for channel_id, channel in scene_t.items()
                if channel
            }
            scene_action.clear()
        for session in active_sessions:
            if time_sync:
                rsp = ServerSceneSyncDataNotice()
                rsp.status = StatusCode.StatusCode_OK
                tmp = rsp.data.add().server_data.add()
                tmp.action_type = SceneActionType.SceneActionType_TOD_UPDATE
                tmp.tod_time = current_tod_time
                session.send(MsgId.ServerSceneSyncDataNotice, rsp, 0)
            for action_notice in pending_scene_actions.get(
                (session.scene_id, session.channel_id), ()
            ):
                session.send(MsgId.ServerSceneSyncDataNotice, action_notice, 0)
        for (scene_id, channel_id), notices in pending_scene_actions.items():
            for action_notice in notices:
                if any(data.player_id < 1010000 for data in action_notice.data):
                    rsend(
                        MsgId.ServerSceneSyncDataNotice,
                        action_notice,
                        [scene_id, channel_id],
                    )

        with lock_chat_msg:
            pending_chat = list(chat_msg)
            chat_msg.clear()
        for session in active_sessions:
            for msg in pending_chat:
                if msg[3].msg.player_id == session.player_id:
                    continue
                match msg[3].type:
                    case ChatChannelType.ChatChannel_Default:
                        if session.scene_id == msg[1] and session.channel_id == msg[2]:
                            session.send(MsgId.ChatMsgNotice, msg[3], 0)
                    case ChatChannelType.ChatChannel_ChatRoom:
                        if session.chat_channel_id == msg[0]:
                            session.send(MsgId.ChatMsgNotice, msg[3], 0)
        for msg in pending_chat:
            if msg[3].msg.player_id < 1010000:
                rsend(MsgId.ChatMsgNotice, msg[3], [msg[0], msg[1], msg[2]])

        with lock_scene:
            with lock_rec_list:
                pending_records = []
                for scene_id, channel_id in rec_list:
                    records = dict(scene[scene_id][channel_id])
                    scene[scene_id][channel_id].clear()
                    pending_records.append((scene_id, channel_id, records))
                rec_list.clear()
        for scene_id, channel_id, records in pending_records:
            rsp = PlayerSceneSyncDataNotice()
            rsp.status = StatusCode.StatusCode_OK
            remote_records = []
            for player_id, record in records.items():
                if player_id < 1010000:
                    tmp = rsp.data.add()
                    tmp.player_id = player_id
                    tmp.data.add().CopyFrom(record)
                else:
                    remote_records.append((player_id, record))
            rsend(1206, rsp, [scene_id, channel_id])
            for player_id, record in remote_records:
                tmp = rsp.data.add()
                tmp.player_id = player_id
                tmp.data.add().CopyFrom(record)
            for session in active_sessions:
                if session.scene_id == scene_id and session.channel_id == channel_id:
                    session.send(MsgId.PlayerSceneSyncDataNotice, rsp, 0)

        if start_t - _last_stamina_sync_time > STAMINA_INTERVAL:
            threading.Thread(
                target=_stamina_sync, args=(active_sessions.copy(),)
            ).start()
            _last_stamina_sync_time = start_t
        use_time = time.time() - start_t
        wait_time = 1.0 / max_tps - use_time
        if use_time > 0.5:
            logger.debug(f"notice sync time: {use_time}")
        if wait_time < 0:
            continue
        if wait_time > 0:
            time.sleep(wait_time)


# 体力恢复节奏 = GlobalConfig.Player_Recover_Vitality_Second(600秒/点);
_vit_tick = False


def _stamina_caps(level):
    """按玩家等级查 Level.player_level 的体力/精力上限, 表缺失兜底 150/800"""
    for e in res["Level"]["player_level"]["datas"]:
        if e["i_d"] == level:
            return (
                e.get("player_vitality", Config.VITALITY_MAX_FALLBACK),
                e.get("player_energy", Config.ENERGY_MAX_FALLBACK),
            )
    return Config.VITALITY_MAX_FALLBACK, Config.ENERGY_MAX_FALLBACK


def _stamina_sync(session_list):
    global _vit_tick
    _vit_tick = not _vit_tick

    for session in session_list:
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
                        db.set_item_detail(
                            session.player_id, item.SerializeToString(), item_id
                        )
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
