from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AcceptQuestReq,
    AcceptQuestRsp,
    StatusCode,
    EQuestType,
    QuestStatus,
)

from utils.res_loader import res
import utils.db as db


@packet_handler(MsgId.AcceptQuestReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AcceptQuestReq()
        req.ParseFromString(data)
        # TODO

        rsp = AcceptQuestRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.quest_type == EQuestType.EQuestType_MainQuest:
            for story in res["Story"]["story"]["datas"]:
                if story["i_d"] == req.quest_id:
                    rsp.quest.ParseFromString(
                        db.get_quest(session.player_id, story["quest_i_d"])
                    )
                    rsp.quest.status = QuestStatus.QuestStatus_InProgress

        session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
