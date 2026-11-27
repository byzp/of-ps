import logging

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import OutFitDyeSaveReq, OutFitDyeSaveRsp, PackNotice, StatusCode

from config import Config
from server import character_growth as growth
import utils.db as db


def _save_price():
    entry = next(
        (
            row
            for row in growth.rows("GlobalConfig", "config")
            if row.get("key") == "Fashion_Customize_Color_Price"
        ),
        None,
    )
    values = entry.get("values", ()) if entry else ()
    if not values:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    value = values[0] if isinstance(values, (tuple, list)) else values
    item_id, separator, count = str(value).partition(":")
    if not separator or not item_id.isdigit():
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    return int(item_id), int(count or 0)

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutFitDyeSaveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutFitDyeSaveReq()
        req.ParseFromString(data)
        rsp = OutFitDyeSaveRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        if not req.is_save_dye_result:
            session.send(MsgId.OutFitDyeSaveRsp, rsp, packet_id)
            return
        try:
            with growth.transaction(session.player_id):
                outfit = growth.load_owned_outfit(session.player_id, req.outfit_id)
                schemes = outfit.main_item.outfit.dye_schemes
                if (
                    req.scheme_index >= Config.MAX_DYE_SCHEME_NUM
                    or req.scheme_index >= len(schemes)
                    or not schemes[req.scheme_index].is_un_lock
                ):
                    raise growth.GrowthError(
                        StatusCode.StatusCode_OUTFIT_SCHEME_INDEX_NOT_UNLOCK
                    )
                costs = growth.normalize_costs((_save_price(),))
                growth.consume(session.player_id, costs, notice)
                scheme = schemes[req.scheme_index]
                color = next(
                    (entry for entry in scheme.colors if entry.pos == req.pos),
                    None,
                )
                if color is None:
                    color = scheme.colors.add()
                    color.pos = req.pos
                color.red = session.color_data[2].red
                color.green = session.color_data[2].green
                color.blue = session.color_data[2].blue
                db.set_item_detail(
                    session.player_id, outfit.SerializeToString(), req.outfit_id
                )
                rsp.scheme_index = req.scheme_index
                rsp.pos_color.CopyFrom(color)
                rsp.is_save_dye_result = True
                rsp.items.add().CopyFrom(outfit)
                notice.items.add().CopyFrom(outfit)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.OutFitDyeSaveRsp, rsp, packet_id)
            return

        session.send(MsgId.OutFitDyeSaveRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
