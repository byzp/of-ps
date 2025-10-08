from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as WorldLevelAchieveList_pb2
import proto.OverField_pb2 as StatusCode_pb2

@packet_handler(CmdId.WorldLevelAchieveListReq)
class WorldLevelAchieveListHandler(PacketHandler):
    def handle(self, session, data: bytes):
        rsp = WorldLevelAchieveList_pb2.WorldLevelAchieveListRsp()
        rsp.status = StatusCode_pb2.StatusCode_Ok
        """
        a1 = rsp.achieves.add()
        a1.achieve_id = 1001
        a1.count = 5

        a2 = rsp.achieves.add()
        a2.achieve_id = 1002
        a2.count = 1

        a3 = rsp.achieves.add()
        a3.achieve_id = 1003
        a3.count = 42

        rsp.unlock_world_levels.extend([1, 2, 5, 10])
        """
        session.send(CmdId.WorldLevelAchieveListRsp, rsp)
