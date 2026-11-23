from handlers.GardenPlaceCharacter import replay_placements

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

        # 花园密码与过期时间
        password, expire_time = db.get_garden_password(session.player_id)
        rsp.garden_info.password = password
        rsp.garden_info.password_expire_time = expire_time

        session.send(MsgId.GetGardenInfoRsp, rsp, packet_id)  # 1685,1686

        # 重放花园已放置角色

        replay_placements(session)
