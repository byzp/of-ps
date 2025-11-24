from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as PlayerBuffNotice_pb2

logger = logging.getLogger(__name__)


"""
# 玩家Buff通知 1880
"""


@packet_handler(CmdId.PlayerBuffNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = PlayerBuffNotice_pb2.PlayerBuffNotice()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Add player buffs
        for buff_data in TEST_DATA["player_buffs"]:
            player_buff = rsp.player_buffs.add()
            player_buff.system_type = buff_data["system_type"]

            # Add buff list
            for buff_item in buff_data["buff_lst"]:
                buff = player_buff.buff_lst.add()
                buff.buff_id = buff_item["buff_id"]
                buff.end_time = buff_item["end_time"]

        session.send(CmdId.PlayerBuffNotice, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "player_buffs": [
        {
            "system_type": 1,
            "buff_lst": [
                {"buff_id": 1001, "end_time": 1763353061},
                {"buff_id": 1001, "end_time": 1763353061},
                {"buff_id": 1001, "end_time": 1763353061},
                {"buff_id": 1001, "end_time": 1763353061},
                {"buff_id": 1001, "end_time": 1763353061},
            ],
        }
    ],
}
