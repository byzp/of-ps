from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as PlayerMainDataRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as ShopInitNotice_pb2
import proto.OverField_pb2 as SceneDataNotice_pb2
import proto.OverField_pb2 as ChatMsgRecordInitNotice_pb2
import proto.OverField_pb2 as ActivitySignInDataNotice_pb2
import proto.OverField_pb2 as ChangeChatChannelRsp_pb2
import proto.OverField_pb2 as IntimacyGiftDayCountNotice_pb2
import proto.OverField_pb2 as AbyssServerRankNotice_pb2
import proto.OverField_pb2 as pb
import utils.db as db
from utils.bin import bin
import server.scene_data as scene_data


@packet_handler(CmdId.PlayerMainDataReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        player_id = session.player_id

        rsp = PlayerMainDataRsp_pb2.PlayerMainDataRsp()
        with open(bin["1006"], "rb") as f:
            rsp.ParseFromString(f.read())

        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.player_id = session.player_id
        rsp.player_name = session.player_name

        rsp.unlock_functions.extend(db.get_unlock_functions(player_id))
        rsp.level = db.get_level(player_id)
        rsp.exp = db.get_exp(player_id)
        session.avatar_id = db.get_avatar(player_id)
        rsp.head = session.avatar_id
        rsp.phone_background = db.get_phone_background(player_id)
        rsp.create_time = db.get_create_time(player_id)

        rsp.ClearField("characters")
        chrp = pb.Character()
        for chr in db.get_characters(player_id):
            chrp.ParseFromString(chr)
            tmp = rsp.characters.add()
            tmp.CopyFrom(chrp)

        rsp.team.char_1, rsp.team.char_2, rsp.team.char_3 = db.get_team_char_id(
            player_id
        )
        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id

        # TODO 任务

        rsp.player_label = player_id
        rsp.channel_label = player_id
        rsp.month_card_over_due_time = db.get_month_card_over_due_time(player_id)
        rsp.garden_likes_num, _, _, _, _ = db.get_garden_info(player_id)
        rsp.month_card_reward_days = db.get_month_card_reward_days(player_id)
        rsp.birthday = db.get_birthday(player_id)
        rsp.is_hide_birthday = db.get_is_hide_birthday(player_id)
        rsp.account_type = db.get_account_type(player_id)

        session.send(CmdId.PlayerMainDataRsp, rsp, True, packet_id)  # 1005,1006

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for item in db.get_item_detail(player_id):
            rsp.items.add().ParseFromString(item)
        rsp.temp_pack_max_size = 30
        session.send(CmdId.PackNotice, rsp, True, packet_id)
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

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1990, rsp)
        session.sbin(1990, bin["1990"], False, packet_id)  # TODO

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1994, rsp)
        session.sbin(1994, bin["1994"], False, packet_id)  # TODO

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2138, rsp)
        session.sbin(2138, bin["2138"], False, packet_id)  # TODO

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2124, rsp)
        session.sbin(2124, bin["2124"], False, packet_id)  # TODO

        session.sbin(2634, bin["2634"], False, packet_id)  # TODO

        rsp = ActivitySignInDataNotice_pb2.ActivitySignInDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(1984, rsp)
        session.sbin(
            CmdId.ActivitySignInDataNotice, bin["1984"], False, packet_id
        )  # TODO

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2584, rsp)
        session.sbin(2584, bin["2584"], False, packet_id)

        rsp = IntimacyGiftDayCountNotice_pb2.IntimacyGiftDayCountNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(CmdId.IntimacyGiftDayCountNotice, rsp, True, packet_id)
        # session.sbin(2658, bin["2658"], False, packet_id)

        rsp = AbyssServerRankNotice_pb2.AbyssServerRankNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(CmdId.AbyssServerRankNotice, rsp, True, packet_id)
        # session.sbin(2648, bin["2648"], False, packet_id)

        session.sbin(1454, bin["1454"], False, packet_id)

        rsp = PackNotice_pb2.PackNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(2630, rsp, True, packet_id)
        # session.sbin(2630, bin["2630"], False, packet_id)

        rsp = SceneDataNotice_pb2.SceneDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        data = rsp.data
        data.scene_id = session.scene_id
        data.players.add().CopyFrom(session.scene_player)

        tmp = pb.ServerSceneSyncDataNotice()
        for i in scene_data.get_and_up_players(
            session.scene_id, session.channel_id, session.player_id
        ):
            tmp.ParseFromString(i)
            data.players.add().CopyFrom(tmp.data[0].server_data[0].player)

        data.channel_id = session.channel_id
        data.tod_time = 0
        data.channel_label = session.channel_id
        session.send(CmdId.SceneDataNotice, rsp, False, packet_id)

        rsp = ChangeChatChannelRsp_pb2.ChangeChatChannelRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.channel_id = session.channel_id
        session.send(CmdId.ChangeChatChannelRsp, rsp, True, packet_id)
        # session.sbin(1931, bin["1931"], False, packet_id)

        for i in db.get_chat_history(player_id):
            rsp = ChatMsgRecordInitNotice_pb2.ChatMsgRecordInitNotice()
            rsp.status = StatusCode_pb2.StatusCode_OK
            rsp.type = i["type"]
            for m in i["msg"]:
                tmp = rsp.msg.add()
                for k, v in m.items():
                    setattr(tmp, k, v)
            session.send(CmdId.ChatMsgRecordInitNotice, rsp, True, packet_id)
        # session.sbin(1938, bin["1938-1"], False, packet_id)
        # session.sbin(1938, bin["1938-2"], False, packet_id)

        # session.sbin(2016, "tmp\\bin\\packet_25_2016_servertoclient_body.bin")
