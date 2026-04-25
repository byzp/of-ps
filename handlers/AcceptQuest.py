from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AcceptQuestReq,
    AcceptQuestRsp,
    StatusCode,
    EQuestType,
    QuestStatus,
    Quest,
    QuestNotice,
)

from utils.res_loader import res
import utils.db as db
from utils.pb_create import make_Quest


@packet_handler(MsgId.AcceptQuestReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AcceptQuestReq()
        req.ParseFromString(data)

        if req.quest_type == EQuestType.EQuestType_MainQuest:
            rsp = AcceptQuestRsp()
            rsp.status = StatusCode.StatusCode_OK
            if req.quest_type == EQuestType.EQuestType_MainQuest:
                for story in res["Story"]["story"]["datas"]:
                    if story["i_d"] == req.quest_id:
                        make_Quest(session.player_id, story["quest_i_d"], rsp.quest)
                        db.set_quest(
                            session.player_id,
                            rsp.quest.quest_id,
                            rsp.quest.SerializeToString(),
                        )
                        session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
                        return
