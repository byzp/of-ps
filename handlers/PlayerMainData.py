import pickle as _pk

import time as _t

from proto.net_pb2 import Buff as _Buff

from proto.net_pb2 import PlayerBuff as _PB

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
    QuestStatus,
    RandomQuestBonus,
    PlayerBuff,
    UnSaveOutfitDyeScheme,
    PlayerQuestionnaireInfo,
    ItemDetail,
    ServerSceneSyncDataNotice,
    SceneActionType,
    PetWarehouseLimitNotice,
    ShopInitNotice,
    PrivateChatOfflineNotice,
    ActivityQuestDataNotice,
    ActivityGiftDataNotice,
    ActivityTurntableDataNotice,
    ActivitySandbagNotice,
    ActivityRegularDataNotice,
    ActivityBattlePassInfoNotice,
    ActivityRecallNotice,
    ActivityKoiNotice,
    IntimacyGiftDayCountNotice,
    AbyssServerRankNotice,
    PlayerBuffNotice,
    ModuleCloseNotice,
    GMRecommendChannelNotice,
)
import utils.db as db
from config import Config
from utils.res_loader import res
from utils.pb_create import make_SceneDataNotice, make_ScenePlayer
from utils import quest_track
from utils import activity_state
from utils import action_unlock
from utils import expression_unlock
from network.remote_link import sync_player
import server.notice_sync as notice_sync
from server.scene_data import up_scene_action
import random
import datetime

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
            "player_name,unlock_functions,level,exp,head,sign,sex,avatar_frame,pendant,world_level,phone_background,create_time,team,birthday,is_hide_birthday,account_type,pet_instance_id,last_login_time",
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
            rsp.pet_instance_id,
            llt,
        ) = infos
        rsp.head = session.avatar_id
        session.player_name = rsp.player_name
        logger.info(f"Player login: {session.player_name}({session.player_id})")
        make_ScenePlayer(session)
        sync_player(session)

        for chr in db.get_characters(player_id):
            rsp.characters.add().ParseFromString(chr)

        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id

        for chapter in db.get_chapter(session.player_id):
            rsp.quest_detail.chapters.add().ParseFromString(chapter)
        # 祈愿开放后登录也恢复当天任务；跨日换组在读取任务列表之前完成。
        daily_tasks = quest_track.start_daily_tasks(session)
        rsp.quest_detail.random_quest_bonus_left.CopyFrom(RandomQuestBonus())
        for quest in db.get_quest(session.player_id):
            tmp = rsp.quest_detail.quests.add()
            tmp.ParseFromString(quest)
            if tmp.status == QuestStatus.QuestStatus_InProgress:
                session.quests[tmp.quest_id] = tmp
        # 无 quest_id 的任务追踪条目
        rsp.quest_detail.quests.extend(activity_state.quest_trackers(player_id))

        rsp.player_buffs.add().system_type = PlayerBuff.BuffSystemType_GLOBAL
        rsp.un_save_outfit_dye_scheme.CopyFrom(UnSaveOutfitDyeScheme())
        if Config.SKIP_QUESTS:
            # 跳过任务模式: 全解锁 + 高倍掉落
            rsp.player_drop_rate_info.kill_drop_rate = 1000
            rsp.player_drop_rate_info.treasure_drop_rate = 1000
        else:
            rsp.player_drop_rate_info.kill_drop_rate = 100
            rsp.player_drop_rate_info.treasure_drop_rate = 100
        rsp.questionnaire_info.CopyFrom(PlayerQuestionnaireInfo())
        rsp.player_label = player_id
        rsp.channel_label = player_id
        rsp.month_card_over_due_time = db.get_month_card_over_due_time(player_id)
        rsp.garden_likes_num, _, _, _, _ = db.get_garden_info(player_id)
        rsp.month_card_reward_days = db.get_month_card_reward_days(player_id)
        if daily_tasks:
            rsp.daily_task.tasks.update(daily_tasks)
            rsp.daily_task.exchange_times_left = 0
        rsp.sp_open_status = True
        rsp.sp_check_status = True
        session.send(MsgId.PlayerMainDataRsp, rsp, packet_id)  # 1005,1006

        # 计算体力和精力的回复
        # last_login_time 统一使用毫秒时间戳。
        now_ms = int(time.time() * 1000)
        elapsed_ms = max(0, now_ms - llt)
        level_row = next(
            (
                row
                for row in res["Level"]["player_level"]["datas"]
                if row["i_d"] == infos[2]
            ),
            {},
        )
        vitality_interval = next(
            (
                int(row["values"][0]) * 1000
                for row in res["GlobalConfig"]["config"]["datas"]
                if row.get("key") == "Player_Recover_Vitality_Second"
            ),
            600_000,
        )
        for item_id, interval_ms, maximum in (
            (10, vitality_interval, level_row.get("player_vitality", 150)),
            (11, 60_000, level_row.get("player_energy", 800)),
        ):
            item = ItemDetail()
            item_b = db.get_item_detail(session.player_id, item_id)
            item.ParseFromString(item_b)
            current_num = max(0, item.main_item.base_item.num)
            if current_num < maximum:
                item.main_item.base_item.num = min(
                    maximum, current_num + elapsed_ms // interval_ms
                )
            db.set_item_detail(session.player_id, item.SerializeToString(), item_id)
        db.set_players_info(session.player_id, "last_login_time", now_ms)

        items_data = db.get_item_detail(session.player_id)
        if items_data:
            items_by_tag = {}

            for item_blob in items_data:
                item = ItemDetail()
                item.ParseFromString(item_blob)
                # 登录是库存快照，不是本次获得物品，不触发首获提示。
                item.main_item.is_new = False
                item_tag = item.main_item.item_tag
                if item_tag not in items_by_tag:
                    items_by_tag[item_tag] = []
                items_by_tag[item_tag].append(item)

            for item_tag, items_in_tag in items_by_tag.items():
                rsp = PackNotice()
                rsp.status = StatusCode.StatusCode_OK
                # rsp.temp_pack_max_size = TEMP_PACK_MAX
                for item in items_in_tag:
                    rsp.items.add().CopyFrom(item)
                session.send(
                    MsgId.PackNotice, rsp, 0
                )  # 按物品类型分组发送items物品数据

        # 场景状态紧随初始物品，功能和活动初始化在其后。
        session.send(MsgId.SceneDataNotice, make_SceneDataNotice(session), 0)

        rsp = ShopInitNotice()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.ShopInitNotice, rsp, 0)

        rsp = PrivateChatOfflineNotice()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.PrivateChatOfflineNotice, rsp, 0)

        activity_state.send_login_notices(session)

        rsp = BlessTreeNotice()
        rsp.status = StatusCode.StatusCode_OK
        for k, v in db.get_bless_tree(session.player_id).items():
            rsp.trees[k].tree_ids.extend(v)
        session.send(MsgId.BlessTreeNotice, rsp, 0)

        # 永久解锁的动作(舞蹈/表情动作道具, kv ns=actions_perm)
        action_unlock.send_perm_notice(session)
        # 已解锁的聊天表情(tag=40 道具, kv ns=expr_perm)
        expression_unlock.send_perm_notice(session)

        for notice_cls, notice_msg_id in (
            (IntimacyGiftDayCountNotice, MsgId.IntimacyGiftDayCountNotice),
            (AbyssServerRankNotice, MsgId.AbyssServerRankNotice),
        ):
            rsp = notice_cls()
            rsp.status = StatusCode.StatusCode_OK
            session.send(notice_msg_id, rsp, 0)

        rsp = PetWarehouseLimitNotice()
        rsp.status = StatusCode.StatusCode_OK
        rsp.warehouse_limit = 100
        session.send(MsgId.PetWarehouseLimitNotice, rsp, packet_id)

        rsp = ModuleCloseNotice()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.ModuleCloseNotice, rsp, 0)

        rsp = GMRecommendChannelNotice()
        rsp.status = StatusCode.StatusCode_OK
        # 运营推荐聊天室与Chat静态频道分类使用不同的数据源。
        for index, channel in enumerate(Config.RECOMMENDED_CHAT_CHANNELS, start=1):
            entry = rsp.channel_list.add(index=index)
            entry.channel_id = channel["channel_id"]
            entry.title = channel.get("title", "")
            entry.image_url = channel.get("image_url", "")
            entry.image_id = channel.get("image_id", "")
        session.send(MsgId.GMRecommendChannelNotice, rsp, 0)

        # 未过期的料理 Buff 重推(LIFE)

        _raw = db.get_kv(player_id, "buffs", "life", b"")
        store = _pk.loads(_raw) if _raw else {}
        now = int(_t.time())
        live = {bid: end for bid, end in store.items() if end > now}
        if live != store:
            db.set_kv(player_id, "buffs", "life", _pk.dumps(live))
        if live:

            bn = PlayerBuffNotice()
            bn.status = StatusCode.StatusCode_OK
            pbk = bn.player_buffs.add()
            pbk.system_type = 2  # BuffSystemType_LIFE
            for bid, end in sorted(live.items()):
                bb = pbk.buff_lst.add()
                bb.buff_id = int(bid)
                bb.end_time = int(end)
            session.send(MsgId.PlayerBuffNotice, bn, 0)

        rsp = ChangeChatChannelRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.channel_id = session.channel_id
        session.send(MsgId.ChangeChatChannelRsp, rsp, packet_id)

        for i in db.get_chat_history(player_id):
            if not i["msg"]:
                continue
            rsp = ChatMsgRecordInitNotice()
            rsp.status = StatusCode.StatusCode_OK
            rsp.type = i["type"]
            for m in i["msg"]:
                tmp = rsp.msg.add()
                for k, v in m.items():
                    setattr(tmp, k, v)
            session.send(MsgId.ChatMsgRecordInitNotice, rsp, packet_id)

        # 视为完成登录，同步场景玩家并广播加入事件
        if session.logged_in == False:
            session.logged_in = True

            notice = ServerSceneSyncDataNotice()
            notice.status = StatusCode.StatusCode_OK
            d = notice.data.add()
            d.player_id = session.player_id
            sd = d.server_data.add()
            sd.action_type = SceneActionType.SceneActionType_ENTER
            sd.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, notice)

            # 同步时间
            rsp = ServerSceneSyncDataNotice()
            rsp.status = StatusCode.StatusCode_OK
            tmp = rsp.data.add().server_data.add()
            tmp.action_type = SceneActionType.SceneActionType_TOD_UPDATE
            tmp.tod_time = int(notice_sync.tod_time)
            session.send(MsgId.ServerSceneSyncDataNotice, rsp, 0)
