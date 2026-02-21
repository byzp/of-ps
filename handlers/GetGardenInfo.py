from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetGardenInfoRsp, StatusCode
import utils.db as db


@packet_handler(MsgId.GetGardenInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetGardenInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        (
            rsp.garden_info.likes_num,
            rsp.garden_info.access_num,
            rsp.garden_info.furniture_num,
            rsp.garden_info.furniture_limit_num,
            rsp.garden_info.is_open,
        ) = db.get_garden_info(session.player_id)

        session.send(MsgId.GetGardenInfoRsp, rsp, packet_id)  # 1685,1686
