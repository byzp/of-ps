import time
import threading
import logging
import server.scene_data
from network.cmd_id import CmdId
import proto.OverField_pb2 as SendActionNotice_pb2
import proto.OverField_pb2 as ServerSceneSyncDataNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as OverField_pb2
import utils.db as db

logger = logging.getLogger(__name__)

max_tps = 120

session_list = []
tod_time = 43200  # 当前游戏内秒（0-86400）
rel_time = 0.0  # 上次现实时间点
last_send_time = 0.0  # 上次同步现实时间点


SPEED_MULTIPLIER = 50.0  # 时间倍率
SEND_INTERVAL_REAL = 60.0  # 时间同步间隔

lock_session = threading.Lock()


def init():
    global rel_time
    rel_time = time.time()
    threading.Thread(target=notice_sync_loop, daemon=True).start()


def notice_sync_loop():
    global session_list, tod_time, rel_time, last_send_time
    while True:
        start_t = time.time()

        with lock_session:
            with server.scene_data.lock_action:
                session_tmp = []
                now = time.time()
                elapsed_real = now - rel_time
                if elapsed_real > 0:
                    tod_time = (tod_time + elapsed_real * SPEED_MULTIPLIER) % 86400.0
                    rel_time = now

                for session in session_list:
                    if session.running == True:
                        session_tmp.append(session)
                    # 1206
                    for k, v in server.scene_data.action.items():
                        if session.user_id == k:
                            continue
                        if session.scene_id == v[0] and session.channel_id == v[1]:
                            # action[user_id]=[scene_id,channel_id,action_id,player_name]
                            rsp = SendActionNotice_pb2.SendActionNotice()
                            rsp.status = StatusCode_pb2.StatusCode_OK
                            rsp.action_id = v[2]
                            rsp.from_player_id = k
                            rsp.from_player_name = v[3]
                            session.send(CmdId.SendActionNotice, rsp, True, 0)
                    # 1208
                    if now - last_send_time >= SEND_INTERVAL_REAL:
                        rsp = ServerSceneSyncDataNotice_pb2.ServerSceneSyncDataNotice()
                        rsp.status = StatusCode_pb2.StatusCode_OK
                        tmp = rsp.data.add().server_data.add()
                        tmp.action_type = OverField_pb2.SceneActionType_TOD_UPDATE
                        tmp.tod_time = int(tod_time)
                        session.send(CmdId.ServerSceneSyncDataNotice, rsp, False, 0)
                        last_send_time = now

                session_list = session_tmp
                server.scene_data.action = {}
        use_time = time.time() - start_t
        wait_time = 1 / max_tps - use_time
        if wait_time > 0:
            time.sleep(wait_time)

        logger.debug(f"notice sync time: {use_time}")

