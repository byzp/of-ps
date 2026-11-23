from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import AreaCloseReq, AreaCloseRsp, StatusCode, AreaData

import utils.db as db

"""
# 区域关闭 1901 1902
"""


@packet_handler(MsgId.AreaCloseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaCloseReq()
        req.ParseFromString(data)

        rsp = AreaCloseRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 读取玩家真实区域数据, 置为关闭状态后回写
        area_b = db.get_area(session.player_id, session.scene_id, req.area_id)
        if area_b:
            rsp.area.ParseFromString(area_b)
        else:
            # 无记录时按 AreaUnlock 惯例从 1 级开始
            rsp.area.level = 1
        rsp.area.area_id = req.area_id
        rsp.area.area_state = AreaData.AreaState.Close
        db.set_area(
            session.player_id,
            session.scene_id,
            req.area_id,
            rsp.area.SerializeToString(),
        )

        session.send(MsgId.AreaCloseRsp, rsp, packet_id)  # 1901,1902
