from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as PlayerMainDataRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as ShopInitNotice_pb2
import proto.OverField_pb2 as SceneDataNotice_pb2
import proto.OverField_pb2 as ServerSceneSyncDataNotice_pb2
import proto.OverField_pb2 as ActivitySignInDataNotice_pb2
import proto.OverField_pb2 as Scene_pb2
import utils.db as db
from utils.bin import bin
import server.scene_data as scene_data


@packet_handler(CmdId.PlayerMainDataReq)
class GetPlayerMainDataHandler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        user_id = session.user_id

        rsp = PlayerMainDataRsp_pb2.PlayerMainDataRsp()

        """ with open(bin["1006"], "rb") as f:
            rsp.ParseFromString(f.read()) """

        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.player_id = db.get_player_id(user_id)
        rsp.player_name = db.get_player_name(user_id)
        # rsp.player_time_offset = 0  # int64
        # rsp.is_today_first_login = False
        rsp.unlock_functions.extend(db.get_unlock_functions(user_id))
        rsp.level = db.get_level(user_id)
        rsp.exp = db.get_exp(user_id)
        rsp.head = db.get_head(user_id)
        # rsp.sign = "hello world"
        rsp.phone_background = db.get_phone_background(user_id)
        # rsp.world_level = 5
        rsp.create_time = db.get_create_time(user_id)
        for chr in db.get_characters(user_id):
            tmp = rsp.characters.add()
            tmp.character_id = chr["character_id"]
            tmp.level = chr["level"]
            tmp.max_level = chr["max_level"]
            for i in chr["equipment_presets"]:
                tmp1 = tmp.equipment_presets.add()
                for k, v in i.items():
                    setattr(tmp1, k, v)
            for i in chr["outfit_presets"]:
                tmp1 = tmp.outfit_presets.add()
                for k, v in i.items():
                    setattr(tmp1, k, v)
            for k, v in chr["character_appearance"].items():
                setattr(tmp.character_appearance, k, v)
            for i in chr["character_skill_list"]:
                tmp1 = tmp.character_skill_list.add()
                for k, v in i.items():
                    setattr(tmp1, k, v)

        rsp.team.char_1, rsp.team.char_2, rsp.team.char_3 = db.get_team(user_id)
        rsp.scene_id = scene_data.get_scene_id(user_id)
        rsp.channel_id = scene_data.get_channel_id(user_id)

        rsp.player_label = user_id
        rsp.channel_label = user_id
        rsp.month_card_over_due_time = db.get_month_card_over_due_time(user_id)
        rsp.garden_likes_num, _, _, _, _ = db.get_garden_info(user_id)
        rsp.month_card_reward_days = db.get_month_card_reward_days(user_id)
        rsp.birthday = db.get_birthday(user_id)
        rsp.account_type = db.get_account_type(user_id)

        # rsp = PlayerMainDataRsp_pb2.PlayerMainDataRsp()
        # with open(bin["1006"], "rb") as f:
        #     rsp.ParseFromString(f.read())
        # rsp.team.char_1=202004
        # rsp.characters[0].character_id=202004
        # rsp.characters[0].equipment_presets[0].weapon=1202101
        session.send(CmdId.PlayerMainDataRsp, rsp, True, packet_id)  # 1005,1006
        # session.sbin(CmdId.PlayerMainDataRsp, "tmp\\bin\\packet_5_1006_servertoclient_body.bin", True, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.ParseFromString(db.get_items(user_id))
        session.send(CmdId.PackNotice, rsp)
        # session.sbin(CmdId.PackNotice, bin["1400"], False, packet_id)

        rsp = ShopInitNotice_pb2.ShopInitNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(CmdId.ShopInitNotice, rsp, False, packet_id)
        # session.sbin(1706, bin["1706"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(CmdId.ChatUnLockExpressionNotice, rsp, False, packet_id)  # 1940

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2010, rsp)
        session.sbin(2010, bin["2010"], False, packet_id)

        """
        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(2634, rsp)
        """

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1990, rsp)
        session.sbin(1990, bin["1990"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1994, rsp)
        session.sbin(1994, bin["1994"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2138, rsp)
        session.sbin(2138, bin["2138"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2124, rsp)
        session.sbin(2124, bin["2124"], False, packet_id)

        session.sbin(2634, bin["2634"], False, packet_id)

        rsp = ActivitySignInDataNotice_pb2.ActivitySignInDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1984, rsp)
        session.sbin(CmdId.ActivitySignInDataNotice, bin["1984"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2584, rsp)
        session.sbin(2584, bin["2584"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2658, rsp)
        session.sbin(2658, bin["2658"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2648, rsp)
        session.sbin(2648, bin["2648"], False, packet_id)

        session.sbin(1454, bin["1454"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2630, rsp)
        session.sbin(2630, bin["2630"], False, packet_id)

        rsp = SceneDataNotice_pb2.SceneDataNotice()
        with open(bin["1016"], "rb") as f:
            rsp.ParseFromString(f.read())

        """ rsp.status = SceneDataNotice_pb2.StatusCode_OK
        dat=rsp.data
        dat.scene_id=scene_data.get_scene_id(user_id)
        gd=dat.scene_garden_data.add()
        gd.likes_num,gd.access_player_num,_,_,_=db.get_garden_info(user_id)
        p=dat.players.add() """
        # rsp.data.players[0].player_id=db.get_player_id(user_id)
        # rsp.data.players[0].player_name=db.get_player_name(user_id)
        rsp.data.players[0].team.char_1.char_id = 202004

        session.send(CmdId.SceneDataNotice, rsp, False, packet_id)
        # session.sbin(1016, bin["1016"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1931, rsp)
        session.sbin(1931, bin["1931"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1938, rsp)
        session.sbin(1938, bin["1938-1"], False, packet_id)
        session.sbin(1938, bin["1938-2"], False, packet_id)

        # session.sbin(2016, "tmp\\bin\\packet_25_2016_servertoclient_body.bin")
