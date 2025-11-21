from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as BossRushInfoReq_pb2
import proto.OverField_pb2 as BossRushInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# BossRush信息 2701 2702
"""


@packet_handler(CmdId.BossRushInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushInfoReq_pb2.BossRushInfoReq()
        req.ParseFromString(data)

        rsp = BossRushInfoRsp_pb2.BossRushInfoRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Set info data
        info = rsp.info
        info.season_id = TEST_DATA["info"]["season_id"]
        info.best_total_score = TEST_DATA["info"]["best_total_score"]
        info.total_rank_ratio = TEST_DATA["info"]["total_rank_ratio"]
        info.current_stage_index = TEST_DATA["info"]["current_stage_index"]
        info.start_time = TEST_DATA["info"]["start_time"]
        info.end_time = TEST_DATA["info"]["end_time"]
        info.show_rank_time = TEST_DATA["info"]["show_rank_time"]
        info.challenge_end_time = TEST_DATA["info"]["challenge_end_time"]

        # Set stage_infos (empty list in this case)
        for stage_info in TEST_DATA["info"]["stage_infos"]:
            stage = info.stage_infos.add()
            # Add stage info fields here if needed

        # Set used_characters (empty list in this case)
        # for character_id in TEST_DATA["info"]["used_characters"]:
        #     rsp.info.used_characters.append(character_id)

        session.send(CmdId.BossRushInfoRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "info": {
        "season_id": 0,
        "best_total_score": 0,
        "total_rank_ratio": 0,
        "current_stage_index": 0,
        "stage_infos": [],
        "start_time": 0,
        "end_time": 0,
        "show_rank_time": 0,
        "challenge_end_time": 0,
        "used_characters": [],
    },
}
