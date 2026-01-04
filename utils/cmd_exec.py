from network.msg_id import MsgId
import logging
import time

import proto.OverField_pb2 as FireworksStartNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

from utils.res_loader import res
from server.scene_data import get_session, lock_scene_action
import server.scene_data as scene_data
import server.notice_sync as notice_sync
import utils.db as db
from utils.pb_create import make_item
from utils.pb_create import make_SceneDataNotice
from network.remote_link import get_connected_servers

logger = logging.getLogger(__name__)


def cmd_exec(cmd: str):
    cmds = cmd.split(" ")
    match cmds[0]:
        case "give":  # give player_id/all item_id [num]
            give(cmds)
        case "firework":
            firework(cmds)  # firework id [dur_time] [start_time]
        case "time":
            # 时间设置为0无效
            set_time(cmds)  # time 1-86400
        case "tp":  # 常规地图
            changeScenechannel(cmds)  # tp player_id/all scene_id [channel_id]
        case "tpd":  # 秘境
            DungeonEnter(cmds)  # tpd player_id/all dungeon_id
        case "kick":
            kick(cmds)  # kick player_id/all
        case "link":
            link(cmds)
        case _:
            logger.warning("Unknow command.")


def link(cmds):
    logger.info(str(get_connected_servers()))


def give(cmds: list):
    match = False
    target_session = []
    if len(cmds) < 3:
        logger.warning("give player_id/all item_id/all [num]")
        return
    else:
        cmds = list(map(lambda x: int(x) if x.lstrip("+-").isdigit() else x, cmds))
    for session in get_session():
        if cmds[1] == "all":
            target_session.append(session)
            match = True
        else:
            if session.player_id == cmds[1]:
                target_session.append(session)
                match = True
                break
    if not match:
        logger.warning("No matching players found.")
        return
    for session in target_session:
        rsp = pb.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["i_d"] == cmds[2] or cmds[2] == "all":
                item = pb.ItemDetail()
                tmp = db.get_item_detail(session.player_id, i["i_d"])
                if not tmp:
                    item.CopyFrom(make_item(i["i_d"], 0, session.player_id))
                else:
                    item.ParseFromString(tmp)
                item.main_item.base_item.num += 1 if len(cmds) < 3 else cmds[3]
                rsp.items.add().CopyFrom(item)
                db.set_item_detail(
                    session.player_id, item.SerializeToString(), i["i_d"]
                )
                if not cmds[2] == "all":
                    break
        session.send(MsgId.PackNotice, rsp, 0)


def firework(cmds):
    if not 2 <= len(cmds) <= 4:
        logger.warning("firework id [dur_time] [start_time]")
        return
    cmds = list(map(lambda x: int(x) if x.lstrip("+-").isdigit() else x, cmds))
    rsp = FireworksStartNotice_pb2.FireworksStartNotice()
    rsp.status = StatusCode_pb2.StatusCode_OK

    fireworks_info = rsp.fireworks_info
    fireworks_info.fireworks_id = cmds[1]
    fireworks_info.fireworks_duration_time = 900
    fireworks_info.fireworks_start_time = int(time.time())
    if len(cmds) == 3:
        fireworks_info.fireworks_duration_time = cmds[2]
        fireworks_info.fireworks_start_time = int(time.time())
    if len(cmds) == 4:
        fireworks_info.fireworks_duration_time = cmds[2]
        fireworks_info.fireworks_start_time = cmds[3]
    for session in get_session():
        session.send(MsgId.FireworksStartNotice, rsp, 0)


def set_time(cmds):
    if not len(cmds) == 2:
        logger.warning("time 1-86400")
        return
    cmds = list(map(lambda x: int(x) if x.lstrip("+-").isdigit() else x, cmds))
    with lock_scene_action:
        notice_sync._last_send_time = 0
        notice_sync.tod_time = cmds[1]


def changeScenechannel(cmds):
    match = False
    target_session = []
    if len(cmds) < 3:
        logger.warning("tp player_id/all scene_id [channel_id]")
        return
    else:
        cmds = list(map(lambda x: int(x) if x.lstrip("+-").isdigit() else x, cmds))
    for session in get_session():
        if cmds[1] == "all":
            target_session.append(session)
            match = True
        else:
            if session.player_id == cmds[1]:
                target_session.append(session)
                match = True
                break
    if not match:
        logger.warning("No matching players found.")
        return

    rsp = pb.ChangeSceneChannelRsp()
    rsp.status = StatusCode_pb2.StatusCode_OK
    rsp.scene_id = cmds[2]
    if len(cmds) > 3:
        rsp.channel_label = cmds[3]
    else:
        rsp.channel_label = 0

    for session in target_session:
        session.send(MsgId.ChangeSceneChannelRsp, rsp, 0)

        notice = pb.ServerSceneSyncDataNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = pb.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)

        rsp = pb.SceneDataNotice()
        rsp.CopyFrom(make_SceneDataNotice(session))
        session.send(MsgId.SceneDataNotice, rsp, 0)

        notice = pb.ServerSceneSyncDataNotice()
        notice.status = pb.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = pb.SceneActionType_ENTER
        sd.player.CopyFrom(session.scene_player)
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)


def DungeonEnter(cmds):
    match = False
    target_session = []
    if len(cmds) < 3:
        logger.warning("tpd player_id/all dungeon_id")
        return
    else:
        cmds = list(map(lambda x: int(x) if x.lstrip("+-").isdigit() else x, cmds))
    for session in get_session():
        if cmds[1] == "all":
            target_session.append(session)
            match = True
        else:
            if session.player_id == cmds[1]:
                target_session.append(session)
                match = True
                break
    if not match:
        logger.warning("No matching players found.")
        return

    for session in target_session:
        rsp = pb.DungeonEnterRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.team.CopyFrom(session.scene_player.team)
        rsp.dungeon_data.dungeon_id = cmds[2]
        rsp.dungeon_data.enter_times = 1
        rsp.dungeon_data.char1 = session.scene_player.team.char1.char_id
        rsp.dungeon_data.char2 = session.scene_player.team.char2.char_id
        rsp.dungeon_data.char3 = session.scene_player.team.char3.char_id
        rsp.dungeon_data.last_enter_time = int(time.time())
        session.send(MsgId.DungeonEnterRsp, rsp, 0)


def kick(cmds: list):
    match = False
    target_session = []
    if len(cmds) < 2:
        logger.warning("kick player_id/all")
        return
    else:
        cmds = list(map(lambda x: int(x) if x.lstrip("+-").isdigit() else x, cmds))
    for session in get_session():
        if cmds[1] == "all":
            target_session.append(session)
            match = True
        else:
            if session.player_id == cmds[1]:
                target_session.append(session)
                match = True
                break
    if not match:
        logger.warning("No matching players found.")
        return
    for session in target_session:
        rsp = pb.PlayerOfflineRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.reason = pb.PlayerOfflineReason_KICK
        session.send(MsgId.PlayerOfflineRsp, rsp, 0)
        # session.close()  # 不能主动断开连接,不然客户端会先提示重连
