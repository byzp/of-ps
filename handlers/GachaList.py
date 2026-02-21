from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GachaListReq, GachaListRsp, StatusCode
from utils.res_loader import res


@packet_handler(MsgId.GachaListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GachaListRsp()
        rsp.status = StatusCode.StatusCode_OK
        for data in res["Gacha"]["info"]["datas"]:
            tmp = rsp.gachas.add()
            tmp.gacha_id = data["i_d"]
            tmp.gacha_times = 120
            tmp.guarantee = 30
        session.send(MsgId.GachaListRsp, rsp, packet_id)  # 1443,1444
