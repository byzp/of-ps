import logging

from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import GenericSceneAReq, GenericSceneARsp, StatusCode
from server import notice_sync
import utils.db as db
from utils import weather
from utils.dungeon_reward import sync_multiplier

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericSceneAReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericSceneAReq()
        req.ParseFromString(data)
        rsp = GenericSceneARsp()
        rsp.generic_msg_id = req.generic_msg_id
        rsp.status = StatusCode.StatusCode_OK

        match req.generic_msg_id:
            case 2:
                if not sync_multiplier(session.player_id, req, rsp):
                    rsp.status = StatusCode.StatusCode_BAD_REQ
            case Config.WEATHER_FORECAST_MESSAGE_ID:
                for hour, weather_type in weather.forecast(notice_sync.game_time_seconds):
                    rsp.params.add(int_value=hour, string_value=str(weather_type))
            case 8:
                stored = db.get_kv(session.player_id, 'preferences', 'hot_channel_skip')
                rsp.params.add().int_value = int(stored or 0)
            case 9:
                if not req.params:
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                else:
                    value = int(req.params[0].int_value)
                    if value not in (0, 1):
                        rsp.status = StatusCode.StatusCode_BAD_REQ
                    else:
                        db.set_kv(session.player_id, 'preferences', 'hot_channel_skip', value)
                        rsp.params.extend(req.params)
            case 1 | 3 | 6:
                rsp.params.extend(req.params)
                for key, value in req.param_map.items():
                    rsp.param_map[key] = value
            case _:
                logger.warning('Unsupported GenericSceneA generic_msg_id=%s', req.generic_msg_id)
                rsp.status = StatusCode.StatusCode_BAD_REQ

        session.send(MsgId.GenericSceneARsp, rsp, packet_id)
