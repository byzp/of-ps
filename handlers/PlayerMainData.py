from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as PlayerMainDataRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as SceneDataNotice_pb2
import proto.OverField_pb2 as ChatMsgRecordInitNotice_pb2
import proto.OverField_pb2 as ActivitySignInDataNotice_pb2
import proto.OverField_pb2 as ChangeChatChannelRsp_pb2
import proto.OverField_pb2 as Quest_pb2
import proto.OverField_pb2 as pb
import utils.db as db
from utils.res_loader import res
import server.scene_data as scene_data


@packet_handler(MsgId.PlayerMainDataReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        player_id = session.player_id

        rsp = PlayerMainDataRsp_pb2.PlayerMainDataRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.player_id = session.player_id
        rsp.player_name = session.player_name

        rsp.unlock_functions.extend(db.get_players_info(player_id, "unlock_functions"))
        rsp.level = db.get_players_info(player_id, "level")
        rsp.exp = db.get_players_info(player_id, "exp")
        session.avatar_id = db.get_players_info(player_id, "head")
        rsp.head = session.avatar_id
        rsp.sign = db.get_players_info(player_id, "sign")
        rsp.sex = db.get_players_info(player_id, "sex")
        rsp.appearance.avatar_frame = db.get_players_info(player_id, "avatar_frame")
        rsp.appearance.pendant = db.get_players_info(player_id, "pendant")
        rsp.world_level = db.get_players_info(player_id, "world_level")

        rsp.phone_background = db.get_players_info(player_id, "phone_background")
        rsp.create_time = db.get_players_info(player_id, "create_time")

        chrp = pb.Character()
        for chr in db.get_characters(player_id):
            chrp.ParseFromString(chr)
            tmp = rsp.characters.add()
            tmp.CopyFrom(chrp)

        rsp.team.char_1, rsp.team.char_2, rsp.team.char_3 = db.get_players_info(
            player_id, "team"
        )
        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id

        for chapter in db.get_chapter(session.player_id):
            tmp = pb.Chapter()
            tmp.ParseFromString(chapter)
            rsp.quest_detail.chapters.add().CopyFrom(tmp)
        rsp.quest_detail.random_quest_bonus_left.CopyFrom(pb.RandomQuestBonus())
        for quest in db.get_quest(session.player_id):
            tmp = Quest_pb2.Quest()
            tmp.ParseFromString(quest)
            rsp.quest_detail.quests.add().CopyFrom(tmp)

        rsp.player_buffs.add().system_type = pb.PlayerBuff.BuffSystemType_GLOBAL
        rsp.un_save_outfit_dye_scheme.CopyFrom(pb.UnSaveOutfitDyeScheme())
        rsp.player_drop_rate_info.kill_drop_rate = 1000
        rsp.player_drop_rate_info.treasure_drop_rate = 1000
        rsp.questionnaire_info.CopyFrom(pb.PlayerQuestionnaireInfo())
        rsp.player_label = player_id
        rsp.channel_label = player_id
        rsp.month_card_over_due_time = db.get_month_card_over_due_time(player_id)
        rsp.garden_likes_num, _, _, _, _ = db.get_garden_info(player_id)
        rsp.month_card_reward_days = db.get_month_card_reward_days(player_id)
        rsp.birthday = db.get_players_info(player_id, "birthday")
        rsp.is_hide_birthday = db.get_players_info(player_id, "is_hide_birthday")
        rsp.account_type = db.get_players_info(player_id, "account_type")
        rsp.daily_task.tasks[1] = 521004  # TODO 随机生成每日月亮任务
        rsp.daily_task.tasks[2] = 521005
        rsp.daily_task.tasks[3] = 521006
        rsp.daily_task.tasks[4] = 521007
        rsp.daily_task.exchange_times_left = 0
        rsp.appearance.CopyFrom(pb.PlayerAppearance())

        session.send(MsgId.PlayerMainDataRsp, rsp, packet_id)  # 1005,1006

        items_data = db.get_item_detail(session.player_id)
        if items_data:
            items_by_tag = {}

            for item_blob in items_data:
                item = PackNotice_pb2.ItemDetail()
                item.ParseFromString(item_blob)
                item_tag = item.main_item.item_tag
                if item_tag not in items_by_tag:
                    items_by_tag[item_tag] = []
                items_by_tag[item_tag].append(item_blob)

            for item_tag, items_in_tag in items_by_tag.items():
                rsp = PackNotice_pb2.PackNotice()
                rsp.status = StatusCode_pb2.StatusCode_OK
                for item_blob in items_in_tag:
                    item = rsp.items.add()
                    item.ParseFromString(item_blob)
                session.send(
                    MsgId.PackNotice, rsp, 0
                )  # 按物品类型分组发送items物品数据

        rsp = ActivitySignInDataNotice_pb2.ActivitySignInDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for activity in res["Activity"]["activity"]["datas"]:
            if activity.get("i_d", 0):
                tmp = rsp.info.add()
                tmp.activity_id = activity["i_d"]
        session.send(MsgId.ActivitySignInDataNotice, rsp, 0)  # TODO

        rsp = SceneDataNotice_pb2.SceneDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        data = rsp.data
        data.scene_id = session.scene_id
        data.players.add().CopyFrom(session.scene_player)

        tmp = pb.ScenePlayer()
        for i in scene_data.get_scene_player(session.scene_id, session.channel_id):
            tmp.ParseFromString(i)
            data.players.add().CopyFrom(tmp)

        data.channel_id = session.channel_id
        data.tod_time = 0
        data.channel_label = session.channel_id
        session.send(MsgId.SceneDataNotice, rsp, 0)

        rsp = ChangeChatChannelRsp_pb2.ChangeChatChannelRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.channel_id = session.channel_id
        session.send(MsgId.ChangeChatChannelRsp, rsp, packet_id)

        for i in db.get_chat_history(player_id):
            rsp = ChatMsgRecordInitNotice_pb2.ChatMsgRecordInitNotice()
            rsp.status = StatusCode_pb2.StatusCode_OK
            rsp.type = i["type"]
            for m in i["msg"]:
                tmp = rsp.msg.add()
                for k, v in m.items():
                    setattr(tmp, k, v)
            session.send(MsgId.ChatMsgRecordInitNotice, rsp, packet_id)
