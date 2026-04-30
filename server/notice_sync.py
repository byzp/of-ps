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
)
from network.msg_id import MsgId
from network.remote_link import rsend
from server.scene_data import (
    _chat_msg as chat_msg,
    lock_chat_msg,
    _action as action,
    lock_action,
    _scene_action as scene_action,
    lock_scene_action,
    _session_list as session_list,
    lock_session,
    _rec_list as rec_list,
    lock_rec_list,
    _scene as scene,
    lock_scene,
    up_scene_action,
)
import utils.db as db

logger = logging.getLogger(__name__)

max_tps = Config.SERVER_MAX_TPS
tod_time = 21600.0
_rel_time = 0.0
_last_send_time = 0.0
_last_stamina_sync_time = 0

SPEED_MULTIPLIER = 50.0
SEND_INTERVAL_REAL = 60.0
STAMINA_INTERVAL = 300

sync_stop = False


def init():
    global _rel_time, _last_stamina_sync_time
    _rel_time = time.time()
    _last_stamina_sync_time = _rel_time
    threading.Thread(target=start_loop, daemon=False).start()


def start_loop():
    status_code = 0
    try:
        notice_sync_loop()
    except Exception as e:
        traceback.print_exc()
        logger.error("A fatal error occurred in notice_sync_loop! Clear and exit.")
        status_code = 1
    finally:
        db.exit()
        os._exit(status_code)


def notice_sync_loop():
    global tod_time, _rel_time, _last_send_time, _last_stamina_sync_time
    while True:
        start_t = time.time()
        with lock_session:
            # 服务器停止
            if sync_stop:
                logger.info("Save player data...")
                # 向所有玩家发送离线通知
                rsp = PlayerOfflineRsp()
                rsp.status = StatusCode.StatusCode_OK
                rsp.reason = PlayerOfflineReason.PlayerOfflineReason_SERVER_SHUTDOWN
                for session in session_list:
                    if session.running == True and session.logged_in == True:
                        session.send(MsgId.PlayerOfflineRsp, rsp, 0)
                # 保存玩家数据
                for session in session_list:
                    if session.logged_in == True:
                        db.set_players_info(
                            session.player_id, "last_login_time", int(start_t)
                        )
                return
            # 检查并清除掉线玩家
            for session in session_list:
                if session.running == False and session.logged_in == True:
                    logger.info(
                        f"Player logout: {session.player_name}({session.player_id})"
                    )
                    # 向其他玩家广播离开事件
                    notice = ServerSceneSyncDataNotice()
                    notice.status = StatusCode.StatusCode_OK
                    d = notice.data.add()
                    d.player_id = session.player_id
                    sd = d.server_data.add()
                    sd.action_type = SceneActionType.SceneActionType_LEAVE
                    up_scene_action(session.scene_id, session.channel_id, notice)

            session_list[:] = [
                s for s in session_list if getattr(s, "running", False)
            ]  # 清除已断开的连接
            elapsed_real = start_t - _rel_time
            if elapsed_real > 0:
                tod_time = (tod_time + elapsed_real * SPEED_MULTIPLIER) % 86400.0
                _rel_time = start_t
            with lock_action:
                # 1970 玩家动作广播
                for ac in action:
                    if ac[2].from_player_id < 1010000:
                        rsend(MsgId.SendActionNotice, ac[2], [ac[0], ac[1]])
                    for session in session_list:
                        # if session.player_id == ac[2].from_player_id:
                        #     continue
                        if session.scene_id == ac[0] and session.channel_id == ac[1]:
                            session.send(MsgId.SendActionNotice, ac[2], 0)
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
                        rsp = ServerSceneSyncDataNotice()
                        rsp.status = StatusCode.StatusCode_OK
                        tmp = rsp.data.add().server_data.add()
                        tmp.action_type = SceneActionType.SceneActionType_TOD_UPDATE
                        tmp.tod_time = int(tod_time)
                        session.send(MsgId.ServerSceneSyncDataNotice, rsp, 0)
                    # 1208 其他事件
                    for i in scene_action[session.scene_id][session.channel_id]:
                        session.send(MsgId.ServerSceneSyncDataNotice, i, 0)
                for scene_id, scene_t in scene_action.items():
                    for channel_id, channel in scene_t.items():
                        for i in channel:
                            for data in i.data:
                                if data.player_id < 1010000:
                                    rsend(MsgId.ServerSceneSyncDataNotice, i, [scene_id, channel_id])
                scene_action.clear()
            with lock_chat_msg:
                for session in session_list:
                    # 聊天信息同步
                    for msg in chat_msg:
                        if msg[3].msg.player_id == session.player_id:
                            continue
                        match msg[3].type:
                            case ChatChannelType.ChatChannel_Default:
                                if (
                                    session.scene_id == msg[1]
                                    and session.channel_id == msg[2]
                                ):
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
                        rsp = PlayerSceneSyncDataNotice()
                        rsp.status = StatusCode.StatusCode_OK
                        oth_notice = []
                        for k, v in scene[scene_id][channel_id].items():
                            if k < 1010000:
                                tmp = rsp.data.add()
                                tmp.player_id = k
                                tmp.data.add().CopyFrom(v)
                            else:
                                oth_notice.append((k, v))
                        rsend(1206, rsp, [scene_id, channel_id])  # 排除其他服务器的
                        for k, v in oth_notice:
                            tmp = rsp.data.add()
                            tmp.player_id = k
                            tmp.data.add().CopyFrom(v)
                        scene[scene_id][channel_id].clear()
                        for session in session_list:
                            if (
                                session.scene_id == scene_id
                                and session.channel_id == channel_id
                            ):
                                session.send(
                                    MsgId.PlayerSceneSyncDataNotice, rsp, 0
                                )  # 1203,1206
                    rec_list.clear()
            if start_t - _last_stamina_sync_time > STAMINA_INTERVAL:
                threading.Thread(
                    target=_stamina_sync, args=(session_list.copy(),)
                ).start()
                _last_stamina_sync_time = start_t
        use_time = time.time() - start_t
        wait_time = 1.0 / max_tps - use_time
        if use_time > 1:
            logger.debug(f"notice sync time: {use_time}")
        if wait_time < 0:
            continue
        if wait_time > 0:
            time.sleep(wait_time)


def _stamina_sync(session_list):
    for session in session_list:
        if session.running and session.logged_in:
            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            item = pack.items.add()
            item_b = db.get_item_detail(session.player_id, 10)  # 体力
            item.ParseFromString(item_b)
            item.main_item.base_item.num += 1
            if item.main_item.base_item.num > 150:
                item.main_item.base_item.num = 150
            db.set_item_detail(session.player_id, item.SerializeToString(), 10)
            item = pack.items.add()
            item_b = db.get_item_detail(session.player_id, 11)  # 精力
            item.ParseFromString(item_b)
            item.main_item.base_item.num += 5
            if item.main_item.base_item.num > 800:
                item.main_item.base_item.num = 800
            db.set_item_detail(session.player_id, item.SerializeToString(), 11)
            session.send(MsgId.PackNotice, pack, 0)
