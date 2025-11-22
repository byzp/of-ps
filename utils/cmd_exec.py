from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetWeaponReq_pb2
import proto.OverField_pb2 as GetWeaponRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

from utils.res_loader import res
from server.scene_data import _session_list as session_list
import utils.db as db

logger = logging.getLogger(__name__)


def cmd_exec(cmd: str):
    cmds = cmd.split(" ")
    if cmds[0] == "give":  # give player_id item_id [num]
        give(cmds)
        return
    else:
        logger.warning("Unknow command.")


def give(cmds: list):
    match = False
    target_session = []
    if len(cmds) < 3:
        logger.warning("give player_id item_id [num]")
        return
    else:
        cmds = list(map(lambda x: int(x) if x.lstrip("+-").isdigit() else x, cmds))
    for session in session_list:
        if session.logged_in and session.running:
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
    all_types = ["all", "character", "gift", "weapon", "armor", "poster"]
    for session in target_session:
        instance_id = db.get_instance_id(session.player_id)
        for i in res["Item"]["item"]["datas"]:
            if i["i_d"] == cmds[2] or cmds[2] in all_types:
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
                if not cmds[2] in all_types:
                    break

        rsp = pb.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for item in db.get_item_detail(session.player_id):
            rsp.items.add().ParseFromString(item)
        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, True, 0)
