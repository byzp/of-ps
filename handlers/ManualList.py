from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ManualListRsp, StatusCode, RewardStatus
from utils.res_loader import res


@packet_handler(MsgId.ManualListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = ManualListRsp()
        rsp.status = StatusCode.StatusCode_OK
        for m in res["Manual"]["manual_dungeon"]["datas"]:
            for f in m["manual_dungeon_items"]:
                tmp = rsp.flags.add()
                tmp.flag_id = f["flag_i_d"]
                tmp.status = RewardStatus.Reward
                tmp.dungeon_task_finish_num = 0
        session.send(MsgId.ManualListRsp, rsp, packet_id)  # 1861,1862
