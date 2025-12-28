from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as CharacterEquipUpdateReq_pb2
import proto.OverField_pb2 as CharacterEquipUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db
from server.scene_data import up_scene_action

logger = logging.getLogger(__name__)


@packet_handler(MsgId.CharacterEquipUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterEquipUpdateReq_pb2.CharacterEquipUpdateReq()
        req.ParseFromString(data)

        rsp = CharacterEquipUpdateReq_pb2.CharacterEquipUpdateRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        ep = req.equipment_preset

        chr = pb.Character()
        chr.ParseFromString(db.get_characters(session.player_id, req.char_id)[0])
        ep1 = chr.equipment_presets[0]  # 装备套装方案目前仅0可用

        if req.char_id in db.get_players_info(session.player_id, "team"):
            # 场景同步
            sy = pb.ServerSceneSyncDataNotice()
            sy.status = StatusCode_pb2.StatusCode_OK
            if ep.weapon != ep1.weapon:
                if ep.weapon:
                    item = pb.ItemDetail()
                    item.ParseFromString(
                        db.get_item_detail(session.player_id, None, ep.weapon)
                    )
                    session.scene_player.team.char1.weapon_id = (
                        item.main_item.item_id
                    )  # 更新场景数据
                    item.main_item.weapon.wearer_id = req.char_id
                    db.set_item_detail(
                        session.player_id, item.SerializeToString(), None, ep.weapon
                    )  # 标记新使用者
                    rsp.items.add().CopyFrom(item)
                if ep1.weapon:
                    item = pb.ItemDetail()
                    item.ParseFromString(
                        db.get_item_detail(session.player_id, None, ep1.weapon)
                    )
                    item.main_item.weapon.wearer_id = 0
                    db.set_item_detail(
                        session.player_id, item.SerializeToString(), None, ep1.weapon
                    )  # 清除旧使用者id
                    rsp.items.add().CopyFrom(item)
            for i in range(0, 4):
                armor = ep.armors[i]
                armor1 = ep1.armors[i]
                if armor.armor_id != armor1.armor_id:
                    if armor.armor_id:
                        item = pb.ItemDetail()
                        item.ParseFromString(
                            db.get_item_detail(session.player_id, None, armor.armor_id)
                        )
                        item.main_item.armor.wearer_id = req.char_id
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            None,
                            armor.armor_id,
                        )
                        rsp.items.add().CopyFrom(item)
                    if armor1.armor_id:
                        item = pb.ItemDetail()
                        item.ParseFromString(
                            db.get_item_detail(session.player_id, None, armor1.armor_id)
                        )
                        item.main_item.armor.wearer_id = 0
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            None,
                            armor1.armor_id,
                        )
                        rsp.items.add().CopyFrom(item)
            for i in range(0, 3):
                poster = ep.posters[i]
                poster1 = ep1.posters[i]
                if poster.poster_id != poster1.poster_id:
                    if poster.poster_id:
                        item = pb.ItemDetail()
                        item.ParseFromString(
                            db.get_item_detail(
                                session.player_id, None, poster.poster_id
                            )
                        )
                        item.main_item.poster.wearer_id = req.char_id
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            None,
                            poster.poster_id,
                        )
                        rsp.items.add().CopyFrom(item)
                    if poster1.poster_id:
                        item = pb.ItemDetail()
                        item.ParseFromString(
                            db.get_item_detail(
                                session.player_id, None, poster1.poster_id
                            )
                        )
                        item.main_item.poster.wearer_id = 0
                        db.set_item_detail(
                            session.player_id,
                            item.SerializeToString(),
                            None,
                            poster1.poster_id,
                        )
                        rsp.items.add().CopyFrom(item)

            data = sy.data.add()
            data.player_id = session.player_id
            tmp = data.server_data.add()
            tmp.action_type = pb.SceneActionType_UPDATE_EQUIP
            tmp.player.CopyFrom(session.scene_player)
            up_scene_action(
                session.scene_id, session.channel_id, sy.SerializeToString()
            )
            # TODO 防具和映像其他玩家看不到，暂时不写同步
        ep1.CopyFrom(ep)
        db.set_character(session.player_id, req.char_id, chr.SerializeToString())
        rsp.character.add().CopyFrom(chr)
        session.send(MsgId.CharacterEquipUpdateRsp, rsp, packet_id)
