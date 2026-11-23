import utils.db as _db

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PackNotice,
    QuestNotice,
    StatusCode,
    TutorialReq,
    TutorialRsp,
)

from config import Config
import utils.db as db
from utils import item_mgr
from utils import flag_state, achieve_track
from utils.pb_create import make_Quest
from utils.reward_resolver import resolve_reward


@packet_handler(MsgId.TutorialReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TutorialReq()
        req.ParseFromString(data)

        with achieve_track.batch(session):
            self._tutorial(session, req, packet_id)

    def _tutorial(self, session, req, packet_id):

        rsp = TutorialRsp()
        rsp.status = StatusCode.StatusCode_OK

        first_open_space_reward = (
            not Config.SKIP_QUESTS
            and req.tutorial_id == 9
            and db.try_claim(session.player_id, "tutorial_reward", "open_space")
        )

        # 教程完成记录(去重计数, kv ns=tutorial)

        if req.tutorial_id:
            key = str(req.tutorial_id)
            done = _db.get_kv(session.player_id, "tutorial", key, 0) or 0
            _db.set_kv(session.player_id, "tutorial", key, int(done) + 1)

        # 引导完成留档(kv ns=tutorial), 供后续条件判定引用
        done = db.get_kv(session.player_id, "tutorial", "ids", b"")
        ids = {x for x in done.decode().split(",") if x}
        ids.add(str(req.tutorial_id))
        db.set_kv(session.player_id, "tutorial", "ids", ",".join(sorted(ids)).encode())

        if first_open_space_reward:
            level_row = db.get_players_info(session.player_id, "level")
            level = level_row[0] if level_row else 1
            reward_list = resolve_reward(600, level)
            if not reward_list:
                reward_list = [(item_id, 1) for item_id in Config.INITIAL_UNLOCK_ITEMS]
            reward_list.append((4050, 1))
            notice = PackNotice()
            notice.status = StatusCode.StatusCode_OK
            item_mgr.grant_items(
                session.player_id,
                reward_list,
                pack_notice=notice,
                session=session,
                unlock_function_ids=Config.TUTORIAL_UNLOCK_FUNCTIONS,
            )

        session.send(MsgId.TutorialRsp, rsp, packet_id)  # 1589,1590
        if first_open_space_reward and notice.items:
            session.send(MsgId.PackNotice, notice, 0)

        if (
            not Config.SKIP_QUESTS
            and req.tutorial_id == 9
            and not db.get_quest(session.player_id, 100011)
        ):
            # 初始空间离开后，正式主线的第一环由服务端主动下发；
            # PlayerMainData 只展示无 quest_id 的追踪条目，不能代替这条
            quest_notice = QuestNotice()
            quest_notice.status = StatusCode.StatusCode_OK
            quest = quest_notice.quests.add()
            make_Quest(session.player_id, 100011, quest)
            db.set_quest(
                session.player_id,
                quest.quest_id,
                quest.SerializeToString(),
            )
            session.quests[quest.quest_id] = quest
            flag_state.unlock_for_quest(session, quest)
            session.send(MsgId.QuestNotice, quest_notice, 0)
