from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as OutfitDyeReq_pb2
import proto.OverField_pb2 as OutfitDyeRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutfitDyeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitDyeReq_pb2.OutfitDyeReq()
        req.ParseFromString(data)

        rsp = OutfitDyeRsp_pb2.OutfitDyeRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.outfit_id = req.outfit_id
        rsp.pos_color.pos = req.pos
        if req.add_rate_color_index:
            color = session.color_data[0].get_color_array(req.uvy, 5)[
                req.add_rate_color_index - 1
            ]
            rsp.pos_color.red = int(color[0])
            rsp.pos_color.green = int(color[1])
            rsp.pos_color.blue = int(color[2])
        else:
            rsp.pos_color.CopyFrom(req.specify_color)
        session.color_data[2].CopyFrom(rsp.pos_color)

        session.send(MsgId.OutfitDyeRsp, rsp, packet_id)
