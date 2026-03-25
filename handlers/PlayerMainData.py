from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time
import logging

from proto.net_pb2 import (
    PlayerMainDataRsp,
    StatusCode,
    PackNotice,
    SceneDataNotice,
    ChatMsgRecordInitNotice,
    ActivitySignInDataNotice,
    ChangeChatChannelRsp,
    BlessTreeNotice,
    Quest,
    Character,
    Chapter,
    RandomQuestBonus,
    PlayerBuff,
    UnSaveOutfitDyeScheme,
    PlayerQuestionnaireInfo,
    PlayerAppearance,
    ItemDetail,
)
import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_SceneDataNotice, make_ScenePlayer
from network.remote_link import sync_player

logger = logging.getLogger(__name__)


@packet_handler(MsgId.PlayerMainDataReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        player_id = session.player_id

        rsp = PlayerMainDataRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.player_id = session.player_id

        infos = db.get_players_info(
            player_id,
            "player_name,unlock_functions,level,exp,head,sign,sex,avatar_frame,pendant,world_level,phone_background,create_time,team,birthday,is_hide_birthday,account_type,last_login_time",
        )
        rsp.unlock_functions.extend(infos[1])
        (
            rsp.player_name,
            _,
            rsp.level,
            rsp.exp,
            session.avatar_id,
            rsp.sign,
            rsp.sex,
            rsp.appearance.avatar_frame,
            rsp.appearance.pendant,
            rsp.world_level,
            rsp.phone_background,
            rsp.create_time,
            [rsp.team.char1, rsp.team.char2, rsp.team.char3],
            rsp.birthday,
            rsp.is_hide_birthday,
            rsp.account_type,
            llt,
        ) = infos
        rsp.head = session.avatar_id
        session.player_name = rsp.player_name
        logger.info(f"Player login: {session.player_name}({session.player_id})")
        make_ScenePlayer(session)
        sync_player(session)

        chrp = Character()
        for chr in db.get_characters(player_id):
            chrp.ParseFromString(chr)
            tmp = rsp.characters.add()
            tmp.CopyFrom(chrp)

        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id

        for chapter in db.get_chapter(session.player_id):
            tmp = Chapter()
            tmp.ParseFromString(chapter)
            rsp.quest_detail.chapters.add().CopyFrom(tmp)
        rsp.quest_detail.random_quest_bonus_left.CopyFrom(RandomQuestBonus())
        for quest in db.get_quest(session.player_id):
            tmp = Quest()
            tmp.ParseFromString(quest)
            rsp.quest_detail.quests.add().CopyFrom(tmp)

        rsp.player_buffs.add().system_type = PlayerBuff.BuffSystemType_GLOBAL
        rsp.un_save_outfit_dye_scheme.CopyFrom(UnSaveOutfitDyeScheme())
        rsp.player_drop_rate_info.kill_drop_rate = 1000
        rsp.player_drop_rate_info.treasure_drop_rate = 1000
        rsp.questionnaire_info.CopyFrom(PlayerQuestionnaireInfo())
        rsp.player_label = player_id
        rsp.channel_label = player_id
        rsp.month_card_over_due_time = db.get_month_card_over_due_time(player_id)
        rsp.garden_likes_num, _, _, _, _ = db.get_garden_info(player_id)
        rsp.month_card_reward_days = db.get_month_card_reward_days(player_id)
        rsp.daily_task.tasks[1] = 521004  # TODO 随机生成每日月亮任务
        rsp.daily_task.tasks[2] = 521005
        rsp.daily_task.tasks[3] = 521006
        rsp.daily_task.tasks[4] = 521007
        rsp.daily_task.exchange_times_left = 0
        rsp.appearance.CopyFrom(PlayerAppearance())
        session.send(MsgId.PlayerMainDataRsp, rsp, packet_id)  # 1005,1006

        # 计算体力和精力的回复
        item = ItemDetail()
        item_b = db.get_item_detail(session.player_id, 10)  # 体力
        item.ParseFromString(item_b)
        item.main_item.base_item.num += int((time.time() - llt) / 300)
        if item.main_item.base_item.num > 150:
            item.main_item.base_item.num = 150
        db.set_item_detail(session.player_id, item.SerializeToString(), 10)
        item_b = db.get_item_detail(session.player_id, 11)  # 精力
        item.ParseFromString(item_b)
        item.main_item.base_item.num += int((time.time() - llt) / 60)
        if item.main_item.base_item.num > 800:
            item.main_item.base_item.num = 800
        db.set_item_detail(session.player_id, item.SerializeToString(), 11)

        items_data = db.get_item_detail(session.player_id)
        if items_data:
            items_by_tag = {}

            for item_blob in items_data:
                item = ItemDetail()
                item.ParseFromString(item_blob)
                item_tag = item.main_item.item_tag
                if item_tag not in items_by_tag:
                    items_by_tag[item_tag] = []
                items_by_tag[item_tag].append(item_blob)

            for item_tag, items_in_tag in items_by_tag.items():
                rsp = PackNotice()
                rsp.status = StatusCode.StatusCode_OK
                for item_blob in items_in_tag:
                    item_t = ItemDetail()
                    item_t.ParseFromString(item_blob)
                    # TODO 临时物品发到邮件
                    item = rsp.items.add().CopyFrom(item_t)
                session.send(
                    MsgId.PackNotice, rsp, 0
                )  # 按物品类型分组发送items物品数据

        rsp = ActivitySignInDataNotice()
        rsp.status = StatusCode.StatusCode_OK
        for activity in res["Activity"]["activity"]["datas"]:
            if activity.get("i_d", 0):
                tmp = rsp.info.add()
                tmp.activity_id = activity["i_d"]
        session.send(MsgId.ActivitySignInDataNotice, rsp, 0)  # TODO

        rsp = BlessTreeNotice()
        rsp.status = StatusCode.StatusCode_OK
        for k, v in db.get_bless_tree(session.player_id).items():
            rsp.trees[k].tree_ids.extend(v)
        session.send(MsgId.BlessTreeNotice, rsp, 0)

        rsp = SceneDataNotice()
        rsp.CopyFrom(make_SceneDataNotice(session))
        session.send(MsgId.SceneDataNotice, rsp, 0)

        rsp = ChangeChatChannelRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.channel_id = session.channel_id
        session.send(MsgId.ChangeChatChannelRsp, rsp, packet_id)

        for i in db.get_chat_history(player_id):
            rsp = ChatMsgRecordInitNotice()
            rsp.status = StatusCode.StatusCode_OK
            rsp.type = i["type"]
            for m in i["msg"]:
                tmp = rsp.msg.add()
                for k, v in m.items():
                    setattr(tmp, k, v)
            session.send(MsgId.ChatMsgRecordInitNotice, rsp, packet_id)
