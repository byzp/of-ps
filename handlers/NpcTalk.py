from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import NpcTalkReq, NpcTalkRsp, StatusCode, PackNotice
from utils.res_loader import res
from utils.pb_create import make_QuestNotice, make_item
import utils.db as db


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
        rsp1 = make_QuestNotice(session, conds)
        if rsp1:
            session.send(MsgId.QuestNotice, rsp1, 0)
        session.send(MsgId.NpcTalkRsp, rsp, packet_id)
        if req.id == 11000311:  # 解锁星云树
            rsp = PackNotice()
            rsp.status = StatusCode.StatusCode_OK
            for i in [100000008, 301]:  # TODO 星符的正常获取
                tmp = rsp.items.add()
                make_item(i, 1, session.player_id, tmp)
                db.set_item_detail(session.player_id, tmp.SerializeToString(), i)
            session.send(MsgId.PackNotice, rsp, 0)
