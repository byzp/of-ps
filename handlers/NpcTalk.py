from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    NpcTalkReq,
    NpcTalkRsp,
    StatusCode,
    QuestNotice,
    QuestStatus,
    AchieveNotice,
    PackNotice,
)
from utils.res_loader import res
import utils.db as db
from utils.pb_create import make_Quest, make_item


@packet_handler(MsgId.NpcTalkReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = NpcTalkReq()
        req.ParseFromString(data)

        rsp = NpcTalkRsp()
        rsp.status = StatusCode.StatusCode_OK
        for i in res["Quest"]["condition_set_group"]["datas"]:
            for i2 in i["quest_condition_set"]:
                if req.id in i2["achieve_condition_i_d"] or req.id in i2.get(
                    "resource_i_d", []
                ):
                    rsp1 = QuestNotice()
                    rsp1.status = StatusCode.StatusCode_OK
                    tmp = rsp1.quests.add()
                    tmp.ParseFromString(db.get_quest(session.player_id, i["i_d"]))
                    cond = True
                    for ii in tmp.conditions:
                        if ii.condition_id == req.id:
                            ii.status = QuestStatus.QuestStatus_Finish
                            db.set_quest(
                                session.player_id,
                                tmp.quest_id,
                                tmp.SerializeToString(),
                            )
                        if ii.status != QuestStatus.QuestStatus_Finish:
                            cond = False
                    if cond:
                        tmp.status = QuestStatus.QuestStatus_Finish
                        f = False
                        for ii in res["Quest"]["quest"]["datas"]:
                            if ii["i_d"] == i["i_d"]:
                                f = True
                                for review in res["Story"]["story_review"]["datas"]:
                                    if (
                                        review["story_review_set"][-1]["dialog_i_d"]
                                        == i["i_d"]
                                    ):
                                        f = False
                                        break
                                continue
                            if f == True:
                                q = rsp1.quests.add()
                                make_Quest(session.player_id, ii["i_d"], q)
                                db.set_quest(
                                    session.player_id,
                                    q.quest_id,
                                    q.SerializeToString(),
                                )
                                break
                    for i3 in i2.get("resource_i_d", []):
                        for i4 in range(len(tmp.conditions) - 1, -1, -1):
                            if tmp.conditions[i4].condition_id == i3:
                                del tmp.conditions[i4]
                    session.send(MsgId.NpcTalkRsp, rsp, packet_id)
                    session.send(MsgId.QuestNotice, rsp1, 0)
                    print(rsp1)
                    return
        session.send(MsgId.NpcTalkRsp, rsp, packet_id)
