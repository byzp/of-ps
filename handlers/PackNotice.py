from tkinter import N
from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb
import utils.db as db
from utils.res_loader import res
from server.scene_data import _session_list as session_list

logger = logging.getLogger(__name__)

num = 10000


@packet_handler(CmdId.PackNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Gift:  # 礼包 tag:1
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Weapon:  # 武器 tag:2
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                weapon = tmp.weapon
                weapon.weapon_id = i["i_d"]
                weapon.instance_id = i["i_d"]
                weapon.attack = 35
                weapon.damage_balance = 0
                weapon.critical_ratio = 0
                weapon.level = 1
                weapon.star = 1
                weapon.property_index = 1
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Armor:  # 防具 tag:3
                # 1100=0, 1200=2, 1300=5, 1400=7, 1500=8
                armor_property_mapping = {1100: 0, 1200: 2, 1300: 5, 1400: 7, 1500: 8}

                # 查找对应的 armor 数据
                armor_data = None
                for armor_item in res["Armor"]["armor"]["datas"]:
                    if armor_item["i_d"] == i["i_d"]:
                        armor_data = armor_item
                        break

                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.is_new = False
                tmp.temp_pack_index = 0
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                armor = tmp.armor
                armor.armor_id = i["i_d"]
                armor.instance_id = i["i_d"]
                if armor_data:
                    armor.main_property_type = armor_property_mapping.get(
                        armor_data["armor_property_i_d"]
                    )  # 主属性还是有问题
                armor.main_property_val = 1000
                armor.wearer_id = 0
                armor.level = 100
                armor.strength_level = 5
                armor.strength_exp = 0
                armor.property_index = 0
                armor.is_lock = False
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Fragment:  # 角色碎片 tag:4
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Poster:  # 映像 tag:5
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                poster = tmp.poster
                poster.poster_id = i["i_d"]
                poster.instance_id = i["i_d"]
                poster.star = 5
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Collection:  # 收藏品 tag:6
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Card:  # 收藏卡 tag:7
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.character.character_id = i["i_d"]
                # 这个好像是多余的角色碎片转换成星辰后，删除角色碎片的通知
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Material:  # 材料 tag:8
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Currency:  # 货币 tag:9
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Food:  # 食物 tag:10
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        # rsp = PackNotice_pb2.PackNotice()
        # rsp.status = StatusCode_pb2.StatusCode_OK
        # for i in res["Item"]["item"]["datas"]:
        #     if i["new_bag_item_tag"] == pb.EBagItemTag_SpellCard: # 未知 tag:11
        #         item_detail = PackNotice_pb2.ItemDetail()
        #         tmp = item_detail.main_item
        #         tmp.item_id = i["i_d"]
        #         tmp.item_tag = i["new_bag_item_tag"]
        #         tmp.base_item.item_id = i["i_d"]
        #         tmp.base_item.num = num
        #         rsp.items.add().CopyFrom(item_detail)

        # rsp.temp_pack_max_size = 30
        # session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Item:  # 普通道具 tag:12
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Fish:  # 鱼产 tag:13
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        # rsp = PackNotice_pb2.PackNotice()
        # rsp.status = StatusCode_pb2.StatusCode_OK
        # for i in res["Item"]["item"]["datas"]:
        #     if i["new_bag_item_tag"] == pb.EBagItemTag_Recipe: # 配方 未知 tag:14
        #         item_detail = PackNotice_pb2.ItemDetail()
        #         tmp = item_detail.main_item
        #         tmp.item_id = i["i_d"]
        #         tmp.item_tag = i["new_bag_item_tag"]
        #         tmp.base_item.item_id = i["i_d"]
        #         tmp.base_item.num = num
        #         rsp.items.add().CopyFrom(item_detail)

        # rsp.temp_pack_max_size = 30
        # session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Baitbox:  # 鱼饵箱 tag:15
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        # rsp = PackNotice_pb2.PackNotice()
        # rsp.status = StatusCode_pb2.StatusCode_OK
        # for i in res["Item"]["item"]["datas"]:
        #     if i["new_bag_item_tag"] == pb.EBagItemTag_Quest: # 任务道具 未知处理方式 tag:16
        #         item_detail = PackNotice_pb2.ItemDetail()
        #         tmp = item_detail.main_item
        #         tmp.item_id = i["i_d"]
        #         tmp.item_tag = i["new_bag_item_tag"]
        #         tmp.base_item.item_id = i["i_d"]
        #         tmp.base_item.num = num
        #         rsp.items.add().CopyFrom(item_detail)

        # rsp.temp_pack_max_size = 30
        # session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Inscription:  # 铭文 tag:17
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.inscription.inscription_id = i["i_d"]
                tmp.inscription.level = 5
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_StrengthStone:  # 强化石 tag:18
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_ExpBook
            ):  # 经验书 能量饮料 tag:19
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Head:  # 头像 tag:20
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

                items = item_detail.SerializeToString()
                db.up_item_detail(session.player_id, items, i["i_d"])

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK

        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Fashion:  # 时装 tag:21
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                outfit = tmp.outfit
                outfit.outfit_id = i["i_d"]
                dye_scheme = outfit.dye_schemes.add()
                dye_scheme.is_un_lock = True
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_UnlockItem:  # 解锁道具 tag:22
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 2  # 1/2
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_AbilityItem:  # 能力道具 tag:23
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_UnlockAbilityItem
            ):  # 解锁能力道具 tag:24
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_CharacterBadge
            ):  # 角色徽章 tag:25
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 8
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_DyeStuff:  # 染料 tag:26
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        # rsp = PackNotice_pb2.PackNotice()
        # rsp.status = StatusCode_pb2.StatusCode_OK
        # for i in res["Item"]["item"]["datas"]:
        #     if i["new_bag_item_tag"] == pb.EBagItemTag_PlayerExp: # 玩家经验 未知处理方式 也许是玩家获得经验 tag:27
        #         item_detail = PackNotice_pb2.ItemDetail()
        #         tmp = item_detail.main_item
        #         tmp.item_id = i["i_d"]
        #         tmp.item_tag = i["new_bag_item_tag"]
        #         tmp.base_item.item_id = i["i_d"]
        #         tmp.base_item.num = num
        #         rsp.items.add().CopyFrom(item_detail)

        # rsp.temp_pack_max_size = 30
        # session.send(CmdId.PackNotice, rsp, False, packet_id)

        # rsp = PackNotice_pb2.PackNotice()
        # rsp.status = StatusCode_pb2.StatusCode_OK
        # for i in res["Item"]["item"]["datas"]:
        #     if i["new_bag_item_tag"] == pb.EBagItemTag_WorldLevel: # 世界等级 未知处理方式 也许是世界等级提升 tag:28
        #         item_detail = PackNotice_pb2.ItemDetail()
        #         tmp = item_detail.main_item
        #         tmp.item_id = i["i_d"]
        #         tmp.item_tag = i["new_bag_item_tag"]
        #         tmp.base_item.item_id = i["i_d"]
        #         tmp.base_item.num = num
        #         rsp.items.add().CopyFrom(item_detail)

        # rsp.temp_pack_max_size = 30
        # session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_Agentia
            ):  # 特殊道具 女装之魂 蔷薇之心 等 tag:29
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_MoonStone
            ):  # 月石 技能材料 tag:30
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

                items = item_detail.SerializeToString()
                db.up_item_detail(session.player_id, items, i["i_d"])

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Umbrella:  # 伞 tag:31
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

                items = item_detail.SerializeToString()
                db.up_item_detail(session.player_id, items, i["i_d"])

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Vitality:  # 体力药剂 tag:32
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Badge:  # 头衔 tag:33
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

                items = item_detail.SerializeToString()
                db.up_item_detail(session.player_id, items, i["i_d"])

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Furniture:  # 家具 tag:34
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Energy:  # 精力药水 tag:35
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        # rsp = PackNotice_pb2.PackNotice()
        # rsp.status = StatusCode_pb2.StatusCode_OK
        # for i in res["Item"]["item"]["datas"]:
        #     if i["new_bag_item_tag"] == pb.EBagItemTag_ShowWeapon: # 显示武器 未知处理方式 tag:36
        #         item_detail = PackNotice_pb2.ItemDetail()
        #         tmp = item_detail.main_item
        #         tmp.item_id = i["i_d"]
        #         tmp.item_tag = i["new_bag_item_tag"]
        #         tmp.base_item.item_id = i["i_d"]
        #         tmp.base_item.num = 1
        #         rsp.items.add().CopyFrom(item_detail)

        # rsp.temp_pack_max_size = 30
        # session.send(CmdId.PackNotice, rsp, False, packet_id)

        # rsp = PackNotice_pb2.PackNotice()
        # rsp.status = StatusCode_pb2.StatusCode_OK
        # for i in res["Item"]["item"]["datas"]:
        #     if i["new_bag_item_tag"] == pb.EBagItemTag_ShowArmor: # 显示防具 未知处理方式 tag:37
        #         item_detail = PackNotice_pb2.ItemDetail()
        #         tmp = item_detail.main_item
        #         tmp.item_id = i["i_d"]
        #         tmp.item_tag = i["new_bag_item_tag"]
        #         tmp.base_item.item_id = i["i_d"]
        #         tmp.base_item.num = 1
        #         rsp.items.add().CopyFrom(item_detail)

        # rsp.temp_pack_max_size = 30
        # session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_TeleportKey
            ):  # 采集空间钥匙 tag:38
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_WallPaper:  # 壁纸 tag:39
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Expression:  # 表情 tag:40
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_MoonCard
            ):  # 月卡通知也许 未发现实际内容 tag:41
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                item_detail.extra_quality = i["quality"]
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_PhoneCase:  # 手机壁纸 tag:42
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

                items = item_detail.SerializeToString()
                db.up_item_detail(session.player_id, items, i["i_d"])

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_Pendant:  # 挂件 tag:43
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

                items = item_detail.SerializeToString()
                db.up_item_detail(session.player_id, items, i["i_d"])

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_AvatarFrame:  # 头像框 tag:44
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = 1
                rsp.items.add().CopyFrom(item_detail)

                items = item_detail.SerializeToString()
                db.up_item_detail(session.player_id, items, i["i_d"])

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_IntimacyGift
            ):  # 亲密度礼物 tag:45
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if i["new_bag_item_tag"] == pb.EBagItemTag_MusicNote:  # 音乐册 tag:46
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_MonthlyCard
            ):  # 月度卡 未知 tag:47
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_BattlePassCard
            ):  # 战斗通行证 未知 tag:48
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_MonthlyGiftCard
            ):  # 月度礼物卡 tag:49
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_BattlePassGiftCard
            ):  # 战斗通行证礼物卡 tag:50
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in res["Item"]["item"]["datas"]:
            if (
                i["new_bag_item_tag"] == pb.EBagItemTag_SeasonalMiniGamesItem
            ):  # 小游戏道具 tag:51
                item_detail = PackNotice_pb2.ItemDetail()
                tmp = item_detail.main_item
                tmp.item_id = i["i_d"]
                tmp.item_tag = i["new_bag_item_tag"]
                tmp.base_item.item_id = i["i_d"]
                tmp.base_item.num = num
                rsp.items.add().CopyFrom(item_detail)

        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, False, packet_id)


# #导入全部测试用
#         rsp = PackNotice_pb2.PackNotice()
#         rsp.status = StatusCode_pb2.StatusCode_OK

#         # 创建或打开文件用于保存打印内容
#         with open("pack_notice_output.txt", "w", encoding="utf-8") as f:
#             for i in res["Item"]["item"]["datas"]:
#                 item = pb.ItemDetail()
#                 tmp = item.main_item
#                 tmp.item_id = i["i_d"]
#                 tmp.item_tag = i["new_bag_item_tag"]
#                 match i["new_bag_item_tag"]:
#                     case _:
#                         tmp.item_tag = i["new_bag_item_tag"]
#                         tmp.base_item.item_id = i["i_d"]
#                         tmp.base_item.num = 100000
#                         rsp.items.add().CopyFrom(item)
#                         # 同时打印到控制台和保存到文件
#                         print(item)
#                         f.write(str(item) + "\n")


#         rsp.temp_pack_max_size = 30
#         session.send(CmdId.PackNotice, rsp, False, packet_id)
