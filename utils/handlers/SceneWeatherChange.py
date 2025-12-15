from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as SceneWeatherChangeNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as WeatherType_pb2

logger = logging.getLogger(__name__)


"""
# 场景天气变化通知 1918
"""


@packet_handler(MsgId.SceneWeatherChangeNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SceneWeatherChangeNotice_pb2.SceneWeatherChangeNotice()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.weather_type = TEST_DATA["weather_type"]

        session.send(MsgId.SceneWeatherChangeNotice, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "weather_type": 1}
