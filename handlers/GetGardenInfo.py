from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as GetGardenInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin
import utils.db as db


@packet_handler(CmdId.GetGardenInfoReq)
class PosterIllustrationListHandler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetGardenInfoRsp_pb2.GetGardenInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        (
            rsp.garden_info.likes_num,
            rsp.garden_info.access_num,
            rsp.garden_info.furniture_num,
            rsp.garden_info.furniture_limit_num,
            rsp.garden_info.is_open,
        ) = db.get_garden_info(session.user_id)

        session.send(CmdId.GetGardenInfoRsp, rsp, False, packet_id)  # 1685,1686
        # session.sbin(1686, bin["1686"])
