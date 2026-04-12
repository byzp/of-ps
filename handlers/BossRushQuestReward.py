from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushQuestRewardReq,
    BossRushQuestRewardRsp,
    ItemDetail,
    StatusCode,
)

from utils.res_loader import res
from utils import db


@packet_handler(MsgId.BossRushQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushQuestRewardReq()
        req.ParseFromString(data)

        rsp = BossRushQuestRewardRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.season_id = req.season_id
        rsp.achieve_id = req.achieve_id

        # 查找对应的成就配置
        achieve_data = None
        season_achieve_id = None

        for season in res["BossRush"]["boss_rush_achieve"]["datas"]:
            if season["i_d"] == req.season_id:
                for achieve_group in season["boss_rush_achieve_group_info"]:
                    if achieve_group["achieve_i_d"] == req.achieve_id:
                        achieve_data = achieve_group
                        season_achieve_id = season["i_d"]
                        break
                break

        if achieve_data:
            # TODO
            pass

        session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
