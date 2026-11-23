from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import NpcTalkReq, NpcTalkRsp, StatusCode
import utils.db as db

from utils import achieve_track
from utils import mail_rewards


@packet_handler(MsgId.NpcTalkReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = NpcTalkReq()
        req.ParseFromString(data)
        mail_rewards.tutorial_reward(session, req.id)

        rsp = NpcTalkRsp()
        rsp.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            # 对话事件一次上报, 模块内部对 37(和[对象]对话)/40(剧情交互节点)
            # 双族扫表判定(两族 id 空间零交集, 只会命中其一);
            achieve_track.report(session, "talk", match=req.id)
            achieve_track.prepare_quests(session)
            session.send(MsgId.NpcTalkRsp, rsp, packet_id)
        # 成就 44(通过【星云树】解锁【二段跳】)由
