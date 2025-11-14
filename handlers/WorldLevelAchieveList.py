from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as WorldLevelAchieveList_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin
from utils.res_loader import res


@packet_handler(CmdId.WorldLevelAchieveListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = WorldLevelAchieveList_pb2.WorldLevelAchieveListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        for dat in res["Level"]["world_level"]["datas"]:
            if dat.get("world_level_info") is not None:
                for i in dat.get("world_level_info"):
                    a_id = i.get("achieve_i_d")
                    if a_id is not None:
                        tmp = rsp.achieves.add()
                        tmp.achieve_id = a_id
                        # TODO achive count
                        if a_id % 2 == 1:
                            tmp.count = 6

        session.send(CmdId.WorldLevelAchieveListRsp, rsp, False, packet_id)  # 1523,1524
        # session.sbin(1524, bin["1524"])
