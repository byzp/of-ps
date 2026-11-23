from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AcceptQuestReq,
    AcceptQuestRsp,
    StatusCode,
    EQuestType,
)

from utils.res_loader import res
import utils.db as db
from utils import flag_state, quest_track
from utils.pb_create import make_Quest


@packet_handler(MsgId.AcceptQuestReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AcceptQuestReq()
        req.ParseFromString(data)

        if req.quest_type != EQuestType.EQuestType_MainQuest:
            rsp = AcceptQuestRsp()
            # 主线请求使用Story ID，其余类型直接使用Quest ID。
            cfg = next(
                (
                    row
                    for row in res["Quest"]["quest"]["datas"]
                    if row["i_d"] == req.quest_id
                    and row.get("new_type", 0) == req.quest_type
                ),
                None,
            )
            if cfg is None:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
                return
            if db.get_quest(session.player_id, req.quest_id):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
                return
            self._accept(session, req.quest_id, rsp, packet_id)
            # 通用成就可能在接取前已经达标，接取后立即同步条件状态。
            quest_track.advance_many(
                session, [c.condition_id for c in rsp.quest.conditions]
            )
            return

        story_cfg = next(
            (s for s in res["Story"]["story"]["datas"] if s["i_d"] == req.quest_id),
            None,
        )
        if not story_cfg:
            rsp = AcceptQuestRsp()
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
            return

        rsp = AcceptQuestRsp()

        quest_id = story_cfg.get("quest_i_d")
        # 已存在同任务(任意状态)时重复接受 → BAD_REQ
        if db.get_quest(session.player_id, quest_id):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
            return

        pre_story = story_cfg.get("pre_story_unlock")

        lv_need = story_cfg.get("lv_unlock") or 1
        row_lv = db.get_players_info(session.player_id, "level")
        if (row_lv[0] if row_lv else 1) < lv_need:
            rsp.status = StatusCode.StatusCode_Lv_Not_Enough
            session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
            return

        chapters = sorted(
            res["Story"]["story_chapter"]["datas"],
            key=lambda c: c.get("i_d") or 0,
        )
        cur_chapter_idx = None
        for idx, c in enumerate(chapters):
            if req.quest_id in c.get("story_list", ()):
                cur_chapter_idx = idx
                break
        if cur_chapter_idx and cur_chapter_idx > 0:
            prev_cfg = chapters[cur_chapter_idx - 1]
            prev_list = prev_cfg.get("story_list", ())
            rewarded_cnt = sum(
                1 for sid in prev_list if db.is_story_rewarded(session.player_id, sid)
            )
            blob_cnt = sum(
                1
                for sid in prev_list
                if db.get_quest(
                    session.player_id,
                    (
                        next(
                            (
                                x.get("quest_i_d")
                                for x in res["Story"]["story"]["datas"]
                                if isinstance(x, dict) and x.get("i_d") == sid
                            ),
                            None,
                        )
                        or 0
                    ),
                )
            )
            if rewarded_cnt < len(prev_list):
                if rewarded_cnt + blob_cnt > 0:
                    rsp.status = StatusCode.StatusCode_PreChapter_Not_Finish
                    session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
                    return
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
                return

        if pre_story and not db.is_story_rewarded(session.player_id, pre_story):
            rsp.status = StatusCode.StatusCode_PreStory_Not_Finish
            session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
            return

        self._accept(session, quest_id, rsp, packet_id)

    def _accept(self, session, quest_id, rsp, packet_id):
        make_Quest(session.player_id, quest_id, rsp.quest)
        db.set_quest(
            session.player_id,
            rsp.quest.quest_id,
            rsp.quest.SerializeToString(),
        )
        session.quests[rsp.quest.quest_id] = rsp.quest
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
        flag_state.unlock_for_quest(session, rsp.quest)
