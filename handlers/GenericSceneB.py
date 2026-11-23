from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GenericSceneBReq, GenericSceneBRsp, StatusCode
from config import Config
from server import notice_sync
from utils import weather

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericSceneBReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericSceneBReq()
        req.ParseFromString(data)

        rsp = GenericSceneBRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.generic_msg_id = req.generic_msg_id
        if req.generic_msg_id == Config.WEATHER_FORECAST_MESSAGE_ID:
            for hour, weather_type in weather.forecast(notice_sync.game_time_seconds):
                rsp.params.add(int_value=hour, string_value=str(weather_type))
        else:
            rsp.params.extend(req.params)
            for key, value in req.param_map.items():
                rsp.param_map[key] = value

        session.send(MsgId.GenericSceneBRsp, rsp, packet_id)  # 2307,2308
