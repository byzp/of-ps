from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import SupplyBoxRewardReq, SupplyBoxRewardRsp, PackNotice, StatusCode
from server import activities
from utils import item_mgr, supply_box  # 保留既有测试/调用方可见的奖励入口


@packet_handler(MsgId.SupplyBoxRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        SupplyBoxRewardReq().ParseFromString(data)
        rsp = SupplyBoxRewardRsp()
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        replayed = activities.claim_supply_box(session.player_id, packet_id, rsp, pack)
        session.send(MsgId.SupplyBoxRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
            if not replayed:
                with activities.achieve_track.batch(session):
                    activities.achieve_track.report(session, "supply_box")
                    activities.report_rewards(session, rsp.items)
