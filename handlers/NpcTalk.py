from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    NpcTalkReq,
    NpcTalkRsp,
    StatusCode,
)
from utils.res_loader import res
from utils.pb_create import make_QuestNotice


@packet_handler(MsgId.NpcTalkReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = NpcTalkReq()
        req.ParseFromString(data)

        rsp = NpcTalkRsp()
        rsp.status = StatusCode.StatusCode_OK
        conds = []
        if req.talk_type == NpcTalkReq.NpcTalkType_Mechanism:
            for i in res["Achieve"]["achieve"]["datas"]:
                if req.id in i.get("param", []):
                    conds.append(i["i_d"])
        else:
            conds.append(req.id)
        rsp1 = make_QuestNotice(session.player_id, conds)
        if rsp1:
            session.send(MsgId.QuestNotice, rsp1, 0)
        session.send(MsgId.NpcTalkRsp, rsp, packet_id)
