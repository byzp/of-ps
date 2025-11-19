from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as BattleEncounterStateUpdateReq_pb2
import proto.OverField_pb2 as BattleEncounterStateUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 战斗遭遇状态更新 1327 1328
"""


@packet_handler(CmdId.BattleEncounterStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BattleEncounterStateUpdateReq_pb2.BattleEncounterStateUpdateReq()
        req.ParseFromString(data)

        rsp = BattleEncounterStateUpdateRsp_pb2.BattleEncounterStateUpdateRsp()

        # 设置状态为成功
        rsp.status = TEST_DATA["status"]

        # 设置encounter数据
        rsp.encounter.battle_id = req.encounter_id  # 取请求的encounter_id
        rsp.encounter.state = req.battle_state  # 取请求的battle_state
        rsp.encounter.box_id = TEST_DATA["encounter"]["box_id"]

        # 设置dynamic_treasure_box_base_info数据
        rsp.dynamic_treasure_box_base_info.box_id = TEST_DATA[
            "dynamic_treasure_box_base_info"
        ]["box_id"]
        rsp.dynamic_treasure_box_base_info.index = TEST_DATA[
            "dynamic_treasure_box_base_info"
        ]["index"]
        rsp.dynamic_treasure_box_base_info.max_quality = TEST_DATA[
            "dynamic_treasure_box_base_info"
        ]["max_quality"]

        session.send(CmdId.BattleEncounterStateUpdateRsp, rsp, False, packet_id)


# 硬编码测试数据
TEST_DATA = {
    "status": 1,
    "encounter": {"box_id": 0},
    "dynamic_treasure_box_base_info": {
        "box_id": 300000,
        "index": 779,
        "max_quality": 2,
    },
}
