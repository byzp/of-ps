from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import WorldLevelAchieveListRsp, StatusCode
from utils.res_loader import res


@packet_handler(MsgId.WorldLevelAchieveListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = WorldLevelAchieveListRsp()
        rsp.status = StatusCode.StatusCode_OK

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

        session.send(MsgId.WorldLevelAchieveListRsp, rsp, packet_id)  # 1523,1524
