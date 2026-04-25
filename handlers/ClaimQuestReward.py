from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ClaimQuestRewardReq,
    ClaimQuestRewardRsp,
    StatusCode,
    PackNotice,
    Chapter,
)

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item


@packet_handler(MsgId.ClaimQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ClaimQuestRewardReq()
        req.ParseFromString(data)

        rsp = ClaimQuestRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        for i in db.get_chapter(session.player_id):
            tmp = Chapter()
            tmp.ParseFromString(i)
            for chapter in res["Story"]["story_chapter"]["datas"]:
                if req.quest_id in chapter["story_list"]:
                    tmp.rewarded_story_ids.append(req.quest_id)
                    db.set_chapter(
                        session.player_id, chapter["i_d"], tmp.SerializeToString()
                    )
                    rsp1 = PackNotice()
                    rsp1.status = StatusCode.StatusCode_OK
                    t1 = rsp.items.add()
                    make_item(101, 100, session.player_id, t1)  # TODO
                    rsp.items.add().CopyFrom(t1)
                    for story in res["Story"]["story"]["datas"]:
                        if story["i_d"] == req.quest_id:
                            rsp.quest.ParseFromString(
                                db.get_quest(session.player_id, story["quest_i_d"])
                            )
                    session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
                    session.send(MsgId.PackNotice, rsp1, 0)
                    return

        # notice = PackNotice()
        # notice.status = StatusCode.StatusCode_OK
        # notice.items.add().CopyFrom(item)
        # session.send(MsgId.PackNotice, notice, packet_id)
