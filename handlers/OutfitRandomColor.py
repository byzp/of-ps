from handlers.OutfitColorantSelect import ensure_swirl

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import random

from proto.net_pb2 import OutfitRandomColorReq, OutfitRandomColorRsp, StatusCode

"""
# 时装随机取色 1653 1654
从当前染剂噪声(session.color_data[0], 由 OutfitColorantSelect 生成)里随机取一个颜色;
结果写入 session.color_data[2] 供 OutFitDyeSave 保存
"""


@packet_handler(MsgId.OutfitRandomColorReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitRandomColorReq()
        req.ParseFromString(data)

        rsp = OutfitRandomColorRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.outfit_id = req.outfit_id

        ensure_swirl(session)
        if session.color_data[0]:
            color = random.choice(session.color_data[0].get_color_array(req.uvy, 5))
            rsp.pos_color.red = int(color[0])
            rsp.pos_color.green = int(color[1])
            rsp.pos_color.blue = int(color[2])
        else:
            # 未选染剂时退化为纯随机颜色
            rsp.pos_color.red = random.randint(0, 255)
            rsp.pos_color.green = random.randint(0, 255)
            rsp.pos_color.blue = random.randint(0, 255)

        # 只更新 rgb, pos 由 OutFitDyeSave 的请求决定
        session.color_data[2].red = rsp.pos_color.red
        session.color_data[2].green = rsp.pos_color.green
        session.color_data[2].blue = rsp.pos_color.blue

        session.send(MsgId.OutfitRandomColorRsp, rsp, packet_id)  # 1653,1654
