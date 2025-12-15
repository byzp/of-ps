from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as QuestNotice_pb2

logger = logging.getLogger(__name__)


"""
# 任务通知 1718
"""


@packet_handler(MsgId.QuestNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = QuestNotice_pb2.QuestNotice()
        req.ParseFromString(data)

        rsp = QuestNotice_pb2.QuestNotice()

        # Set data from hardcoded test data
        rsp.status = TEST_DATA["parsed_result"]["status"]

        # Add quests
        for quest_data in TEST_DATA["parsed_result"]["quests"]:
            quest = rsp.quests.add()
            quest.quest_id = quest_data["quest_id"]
            quest.status = quest_data["status"]
            quest.complete_count = quest_data["complete_count"]
            quest.bonus_times = quest_data["bonus_times"]
            quest.activity_id = quest_data["activity_id"]

            # Add conditions
            for condition_data in quest_data["conditions"]:
                condition = quest.conditions.add()
                condition.condition_id = condition_data["condition_id"]
                condition.progress = condition_data["progress"]
                condition.status = condition_data["status"]

        # Set daily quest bonus info
        daily_bonus = TEST_DATA["parsed_result"]["daily_quest_day_bonus_info"]
        rsp.daily_quest_day_bonus_info.bonus_1_left = daily_bonus["bonus_1_left"]
        rsp.daily_quest_day_bonus_info.bonus_2_left = daily_bonus["bonus_2_left"]
        rsp.daily_quest_day_bonus_info.bonus_3_left = daily_bonus["bonus_3_left"]

        # Set random quest bonus info
        random_bonus = TEST_DATA["parsed_result"]["random_quest_bonus_info"]
        rsp.random_quest_bonus_info.bonus_left = random_bonus["bonus_left"]

        session.send(MsgId.QuestNotice, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "parsed_result": {
        "status": 1,
        "quests": [
            {
                "quest_id": 0,
                "conditions": [{"condition_id": 20010021, "progress": 0, "status": 1}],
                "status": 1,
                "complete_count": 0,
                "bonus_times": 1,
                "activity_id": 0,
            }
        ],
        "daily_quest_day_bonus_info": {
            "bonus_1_left": 3,
            "bonus_2_left": 5,
            "bonus_3_left": 9,
        },
        "random_quest_bonus_info": {"bonus_left": 0},
    }
}
