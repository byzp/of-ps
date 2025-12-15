from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GMRecommendChannelNotice_pb2

logger = logging.getLogger(__name__)


"""
# GM推荐频道通知 2630
"""


@packet_handler(MsgId.GMRecommendChannelNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GMRecommendChannelNotice_pb2.GMRecommendChannelNotice()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Add channel list
        for channel_data in TEST_DATA["channel_list"]:
            channel = rsp.channel_list.add()
            channel.index = channel_data["index"]
            channel.channel_id = channel_data["channel_id"]
            channel.image_url = channel_data["image_url"]
            channel.image_id = channel_data["image_id"]
            channel.title = channel_data["title"]

        session.send(MsgId.GMRecommendChannelNotice, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "channel_list": [
        {
            "index": 1,
            "channel_id": 2898681,
            "image_url": "http://webgm-of.inutan.com/2025-11-14/a767b047-f59e-4d46-adcb-414f9b9ed9c8.png",
            "image_id": "a767b047-f59e-4d46-adcb-414f9b9ed9c8",
            "title": "小那由",
        },
        {
            "index": 2,
            "channel_id": 8984255,
            "image_url": "http://webgm-of.inutan.com/2025-11-14/0efd2dae-83b2-4042-a660-9033099d23df.png",
            "image_id": "0efd2dae-83b2-4042-a660-9033099d23df",
            "title": "棠霜",
        },
        {
            "index": 3,
            "channel_id": 1968756,
            "image_url": "http://webgm-of.inutan.com/2025-11-14/50b4dc4c-5601-4134-b33a-984138ffb415.png",
            "image_id": "50b4dc4c-5601-4134-b33a-984138ffb415",
            "title": "HC",
        },
        {
            "index": 4,
            "channel_id": 1436700,
            "image_url": "http://webgm-of.inutan.com/2025-11-14/30e46d7f-0a02-41c9-91de-f7ea0d04d7a1.png",
            "image_id": "30e46d7f-0a02-41c9-91de-f7ea0d04d7a1",
            "title": "丽波凌",
        },
    ],
}
