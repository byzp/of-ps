from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as AcceptQuestReq_pb2
import proto.OverField_pb2 as AcceptQuestRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

from utils.res_loader import res
import utils.db as db


@packet_handler(MsgId.AcceptQuestReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AcceptQuestReq_pb2.AcceptQuestReq()
        req.ParseFromString(data)
        # TODO

        rsp = AcceptQuestRsp_pb2.AcceptQuestRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        if req.quest_type == pb.EQuestType_MainQuest:
            for story in res["Story"]["story"]["datas"]:
                if story["i_d"] == req.quest_id:
                    rsp.quest.ParseFromString(
                        db.get_quest(session.player_id, story["quest_i_d"])
                    )
                    rsp.quest.status = pb.QuestStatus_InProgress

        session.send(MsgId.AcceptQuestRsp, rsp, packet_id)
