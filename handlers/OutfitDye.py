from handlers.OutfitColorantSelect import ensure_swirl

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import OutfitDyeReq, OutfitDyeRsp, PackNotice, StatusCode

from server import character_growth as growth
from utils import achieve_track
import utils.db as db


def _dye_cost():
    entry = next(
        (
            row
            for row in growth.rows("GlobalConfig", "config")
            if row.get("key") == "Fashion_DyeStuff_Num"
        ),
        None,
    )
    values = entry.get("values", ()) if entry else ()
    if not values:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    value = values[0] if isinstance(values, (tuple, list)) else values
    count = int(value or 0)
    if count <= 0:
        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    return count


@packet_handler(MsgId.OutfitDyeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitDyeReq()
        req.ParseFromString(data)
        rsp = OutfitDyeRsp(status=StatusCode.StatusCode_OK, outfit_id=req.outfit_id)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                outfit = growth.load_owned_outfit(session.player_id, req.outfit_id)
                schemes = outfit.main_item.outfit.dye_schemes
                if req.scheme_index >= len(schemes) or not schemes[req.scheme_index].is_un_lock:
                    raise growth.GrowthError(
                        StatusCode.StatusCode_OUTFIT_SCHEME_INDEX_NOT_UNLOCK
                    )
                colorant = int(
                    db.get_kv(session.player_id, "outfit_dye", "selected_colorant", 0) or 0
                )
                cfg = growth.item_config(colorant)
                dye_cfg = next(
                    (
                        row
                        for row in growth.rows("DyeStuff", "dye_data")
                        if row.get("i_d") == colorant
                    ),
                    None,
                )
                if (
                    not colorant
                    or cfg is None
                    or cfg.get("new_bag_item_tag") != 26
                    or dye_cfg is None
                ):
                    raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
                costs = [(colorant, _dye_cost())]
                growth.consume(session.player_id, costs, notice)
                count = int(db.get_kv(session.player_id, "outfit_dye", "guarantee", 0) or 0)
                count = 0 if count >= 10 else count + 1
                db.set_kv(session.player_id, "outfit_dye", "guarantee", count)
                rsp.total_guarantee_dye_num = count
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.OutfitDyeRsp, rsp, packet_id)
            return

        ensure_swirl(session)
        color_array = session.color_data[0].get_color_array(req.uvy, 5)
        if 0 < req.add_rate_color_index <= len(color_array):
            color = color_array[req.add_rate_color_index - 1]
            rsp.pos_color.red = int(color[0])
            rsp.pos_color.green = int(color[1])
            rsp.pos_color.blue = int(color[2])
        else:
            rsp.pos_color.CopyFrom(req.specify_color)
        rsp.pos_color.pos = req.pos
        session.color_data[2].CopyFrom(rsp.pos_color)
        session.send(MsgId.OutfitDyeRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        achieve_track.report(session, "outfit_dye")
