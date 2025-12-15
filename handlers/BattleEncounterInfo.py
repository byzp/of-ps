from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as BattleEncounterInfoReq_pb2
import proto.OverField_pb2 as BattleEncounterInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 战斗遭遇信息 1329 1330
"""


@packet_handler(MsgId.BattleEncounterInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BattleEncounterInfoReq_pb2.BattleEncounterInfoReq()
        req.ParseFromString(data)

        rsp = BattleEncounterInfoRsp_pb2.BattleEncounterInfoRsp()

        rsp.status = TEST_DATA["status"]

        # 根据请求中的encounter_ids数量返回对应数量的encounters
        for i, encounter_id in enumerate(req.encounter_ids):
            encounter = rsp.encounters.add()
            encounter.battle_id = encounter_id  # 使用请求中的ID
            encounter.state = TEST_DATA["state"]  # 设置为Close状态
            # 第一个encounter的box_id为300000，其余为0
            encounter.box_id = (
                TEST_DATA["box_id_first"] if i == 0 else TEST_DATA["box_id_other"]
            )

        session.send(MsgId.BattleEncounterInfoRsp, rsp, packet_id)


# 硬编码测试数据
TEST_DATA = {
    "status": 1,  # StatusCode.OK
    "state": 4,  # BattleState.Close
    "box_id_first": 300000,
    "box_id_other": 0,
}
