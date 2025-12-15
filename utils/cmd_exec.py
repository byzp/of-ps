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
        case "tp":
            changeScenechannel(cmds)  # tp player_id/all scene_id [channel_id]
        case _:
            logger.warning("Unknow command.")


def give(cmds: list):
    match = False
    target_session = []
    if len(cmds) < 3:
        logger.warning("give player_id/all item_id [num]")
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
        instance_id = db.get_instance_id(session.player_id)
        for i in res["Item"]["item"]["datas"]:
            if i["i_d"] == cmds[2] or cmds[2] == "all":
                item = pb.ItemDetail()
                itemb = db.get_item_detail(session.player_id, i["i_d"])
                if itemb:
                    item.ParseFromString(itemb)
                tmp = item.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                match i["new_bag_item_tag"]:
                    case pb.EBagItemTag_Gift:
                        tmp.base_item.item_id = i["i_d"]
                        db.set_item_detail(
                            session.player_id, item.SerializeToString(), i["i_d"]
                        )
                    case pb.EBagItemTag_Weapon:
                        weapon = tmp.weapon
                        weapon.weapon_id = i["i_d"]
                        weapon.instance_id = instance_id
                        weapon.attack = 35
                        weapon.damage_balance = 0  # 平衡
                        weapon.critical_ratio = 0  # 暴击
                        # weapon.wearer_id = #已装备的角色id
                        weapon.level = 1
                        # weapon.strength_level=5
                        weapon.star = 1
                        weapon.property_index = 1
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            None,
                            instance_id,
                        )
                        instance_id += 1
                    case pb.EBagItemTag_Armor:
                        armor = tmp.armor
                        armor.armor_id = i["i_d"]
                        armor.instance_id = instance_id
                        armor.main_property_type = pb.EPropertyType_MaxHP
                        armor.main_property_val = 100
                        armor.level = 100
                        armor.property_index = 1
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            None,
                            instance_id,
                        )
                        instance_id += 1
                    case pb.EBagItemTag_Poster:
                        poster = tmp.poster
                        poster.poster_id = i["i_d"]
                        poster.instance_id = instance_id
                        poster.star = 1
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            None,
                            instance_id,
                        )
                        instance_id += 1
                    case pb.EBagItemTag_Fashion:  # 时装
                        outfit = tmp.outfit
                        outfit.outfit_id = i["i_d"]
                        tmp = outfit.dye_schemes.add()
                        tmp.is_un_lock = True
                        items = item.SerializeToString()
                        db.set_item_detail(
                            session.player_id, item.SerializeToString(), i["i_d"]
                        )
                    case pb.EBagItemTag_Card:
                        pass
                    case pb.EBagItemTag_SpellCard:
                        pass
                    case pb.EBagItemTag_Fish:
                        pass
                    case pb.EBagItemTag_Recipe:
                        pass
                    case (
                        _
                    ):  # Fragment, Collection, Material, Currency, Food, Item, Head,
                        tmp.base_item.item_id = i["i_d"]
                        if len(cmds) >= 4:
                            tmp.base_item.num += cmds[3]
                        else:
                            tmp.base_item.num += 1
                        items = item.SerializeToString()
                        db.set_item_detail(session.player_id, items, i["i_d"])
                if not cmds[2] == "all":
                    break

        rsp = pb.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for item in db.get_item_detail(session.player_id):
            rsp.items.add().ParseFromString(item)
        rsp.temp_pack_max_size = 30
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
        scene_data.up_scene_action(
            session.scene_id, session.channel_id, notice.SerializeToString()
        )

        tmp = pb.SceneDataNotice()
        tmp.status = StatusCode_pb2.StatusCode_OK
        data = tmp.data
        data.scene_id = session.scene_id
        data.players.add().CopyFrom(session.scene_player)

        tmp1 = pb.ScenePlayer()
        for i in scene_data.get_scene_player(session.scene_id, session.channel_id):
            tmp1.ParseFromString(i)
            data.players.add().CopyFrom(tmp1)

        data.channel_id = session.channel_id
        data.tod_time = 0
        data.channel_label = session.channel_id
        session.send(MsgId.SceneDataNotice, tmp, 0)

        notice = pb.ServerSceneSyncDataNotice()
        notice.status = pb.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = pb.SceneActionType_ENTER
        sd.player.CopyFrom(session.scene_player)
        res = notice.SerializeToString()
        scene_data.up_scene_action(session.scene_id, session.channel_id, res)
