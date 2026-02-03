from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as OutFitDyeSaveReq_pb2
import proto.OverField_pb2 as OutFitDyeSaveRsp_pb2
import proto.OverField_pb2 as ItemDetail_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutFitDyeSaveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutFitDyeSaveReq_pb2.OutFitDyeSaveReq()
        req.ParseFromString(data)

        rsp = OutFitDyeSaveRsp_pb2.OutFitDyeSaveRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        if req.is_save_dye_result:  # TODO 自定义染色消耗星石
            rsp.scheme_index = req.scheme_index
            rsp.pos_color.CopyFrom(session.color_data[2])
            rsp.is_save_dye_result = True
            outfit = ItemDetail_pb2.ItemDetail()
            outfit.ParseFromString(db.get_item_detail(session.player_id, req.outfit_id))
            find = False
            for color in outfit.main_item.outfit.dye_schemes[req.scheme_index].colors:
                if color.pos == req.pos:
                    color.red = session.color_data[2].red
                    color.green = session.color_data[2].green
                    color.blue = session.color_data[2].blue
                    find = True
                    break
            if not find:
                color = outfit.main_item.outfit.dye_schemes[
                    req.scheme_index
                ].colors.add()
                color.CopyFrom(session.color_data[2])
                color.pos = req.pos
            db.set_item_detail(
                session.player_id, outfit.SerializeToString(), req.outfit_id
            )
            rsp.items.add().CopyFrom(outfit)
        session.send(MsgId.OutFitDyeSaveRsp, rsp, packet_id)
