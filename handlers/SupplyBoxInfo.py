from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as SupplyBoxInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin
import utils.db as db


@packet_handler(CmdId.SupplyBoxInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SupplyBoxInfoRsp_pb2.SupplyBoxInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.next_reward_time = db.get_SupplyBox_next_reward_time(session.user_id)

        session.send(CmdId.SupplyBoxInfoRsp, rsp, False, packet_id)  # 1891,1892
        # session.sbin(1892, bin["1892"])
