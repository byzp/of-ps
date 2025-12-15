import time
import threading
import logging
import os
import traceback

from config import Config
from proto import OverField_pb2 as OverField_pb2
import proto.OverField_pb2 as SendActionNotice_pb2
import proto.OverField_pb2 as ServerSceneSyncDataNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb
from network.msg_id import MsgId
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

SPEED_MULTIPLIER = 50.0
SEND_INTERVAL_REAL = 60.0

sync_stop = False


def init():
    global _rel_time
    _rel_time = time.time()
    threading.Thread(target=start_loop, daemon=False).start()


def start_loop():
    status_code = 0
    try:
        notice_sync_loop()
    except Exception as e:
        print(traceback.format_exc())
        logger.error("A fatal error occurred in notice_sync_loop! Clear and exit.")
        status_code = 1
    finally:
        db.exit()
        time.sleep(1)
        os._exit(status_code)


def notice_sync_loop():
    global tod_time, _rel_time, _last_send_time
    while True:
        start_t = time.time()
        with lock_session:
            # 服务器停止
            if sync_stop:
                logger.info("Save player data...")
                # 向所有玩家发送离线通知
                rsp = pb.PlayerOfflineRsp()
                rsp.status = StatusCode_pb2.StatusCode_OK
                rsp.reason = pb.PlayerOfflineReason_SERVER_SHUTDOWN
                for session in session_list:
                    if session.running == True and session.logged_in == True:
                        session.send(MsgId.PlayerOfflineRsp, rsp, 0)
                # 保存玩家数据
                for session in session_list:
                    if session.logged_in == True:
                        pass
                return
            # 检查并清除掉线玩家
            for session in session_list:
                if session.running == False and session.logged_in == True:
                    logger.info(
                        f"Player logout: {session.player_name}({session.player_id})"
                    )
                    # 向其他玩家广播离开事件
                    notice = ServerSceneSyncDataNotice_pb2.ServerSceneSyncDataNotice()
                    notice.status = StatusCode_pb2.StatusCode_OK
                    d = notice.data.add()
                    d.player_id = session.player_id
                    sd = d.server_data.add()
                    sd.action_type = pb.SceneActionType_LEAVE
                    up_scene_action(
                        session.scene_id, session.channel_id, notice.SerializeToString()
                    )

            session_list[:] = [
                s for s in session_list if getattr(s, "running", False)
            ]  # 清除已断开的连接
            now = time.time()
            elapsed_real = now - _rel_time
            if elapsed_real > 0:
                tod_time = (tod_time + elapsed_real * SPEED_MULTIPLIER) % 86400.0
                _rel_time = now
            with lock_action:
                for session in session_list:
                    # 1970 玩家动作广播
                    for k, v in action.items():
                        if session.player_id == k:
                            continue
                        if session.scene_id == v[0] and session.channel_id == v[1]:
                            rsp = SendActionNotice_pb2.SendActionNotice()
                            rsp.status = StatusCode_pb2.StatusCode_OK
                            rsp.action_id = v[2]
                            rsp.from_player_id = k
                            rsp.from_player_name = v[3]
                            session.send(MsgId.SendActionNotice, rsp, 0)
                action.clear()
            with lock_scene_action:
                if now - _last_send_time >= SEND_INTERVAL_REAL:
                    time_sync = True
                    _last_send_time = now
                else:
                    time_sync = False
                for session in session_list:
                    # 1208 场景时间同步
                    if time_sync:
                        rsp = ServerSceneSyncDataNotice_pb2.ServerSceneSyncDataNotice()
                        rsp.status = StatusCode_pb2.StatusCode_OK
                        tmp = rsp.data.add().server_data.add()
                        tmp.action_type = OverField_pb2.SceneActionType_TOD_UPDATE
                        tmp.tod_time = int(tod_time)
                        session.send(MsgId.ServerSceneSyncDataNotice, rsp, 0)
                    # 1208 其他事件
                    for i in scene_action[session.scene_id][session.channel_id]:
                        # 消除额外操作以节省性能
                        session.send(MsgId.ServerSceneSyncDataNotice, i, 0, True)
                scene_action.clear()
            with lock_chat_msg:
                for session in session_list:
                    # 聊天信息同步
                    for msg in chat_msg["default"][session.scene_id][
                        session.channel_id
                    ]:
                        if msg[1] == session.player_id:
                            continue
                        rsp = pb.ChatMsgNotice()
                        rsp.status = StatusCode_pb2.StatusCode_OK
                        rsp.msg.player_id = msg[1]
                        rsp.msg.head = session.avatar_id
                        rsp.msg.badge = session.badge_id
                        rsp.msg.name = session.player_name
                        if msg[0]:
                            rsp.msg.text = msg[2]
                        else:
                            rsp.msg.expression = msg[2]
                        rsp.msg.send_time = int(time.time() * 1000)
                        session.send(MsgId.ChatMsgNotice, rsp, 0)
                chat_msg.clear()
            with lock_scene:
                with lock_rec_list:
                    # 玩家动作同步
                    for scene_id, channel_id in rec_list:
                        rsp = OverField_pb2.PlayerSceneSyncDataNotice()
                        rsp.status = StatusCode_pb2.StatusCode_OK
                        for k, v in scene[scene_id][channel_id].items():
                            tmp = rsp.data.add()
                            tmp.player_id = k
                            tmp.data.add().ParseFromString(v)
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

        use_time = time.time() - start_t
        wait_time = 1.0 / max_tps - use_time
        if use_time > 0.001:
            logger.debug(f"notice sync time: {use_time}")
        if wait_time < 0:
            continue
        if wait_time > 0:
            time.sleep(wait_time)
