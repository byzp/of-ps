from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    OutFitDyeSaveReq,
    OutFitDyeSaveRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)

import logging

import utils.db as db
from utils.trace import trace
from utils.res_loader import res
from utils import item_mgr

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutFitDyeSaveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutFitDyeSaveReq()
        req.ParseFromString(data)

        rsp = OutFitDyeSaveRsp()
        pack = None

        import config as _cfg
        if req.is_save_dye_result and not getattr(_cfg.Config, 'DYE_NO_COST', False):
            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            _price = next(
                (
                    e.get("values")
                    for e in res["GlobalConfig"]["config"]["datas"]
                    if e.get("key") == "Fashion_Customize_Color_Price"
                ),
                "102:100",
            )
            if isinstance(_price, (list, tuple)):
                _price = _price[0]
            _pid, _, _pnum = str(_price).partition(":")
            if not item_mgr.consume_items(
                session.player_id,
                [(int(_pid), int(_pnum or 100))],
                pack_notice=pack,
                session=session,
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.OutFitDyeSaveRsp, rsp, packet_id)
                return

        rsp.status = StatusCode.StatusCode_OK

        if req.is_save_dye_result:
            rsp.scheme_index = req.scheme_index
            rsp.pos_color.CopyFrom(session.color_data[2])
            rsp.is_save_dye_result = True
            _blob = db.get_item_detail(session.player_id, req.outfit_id)
            if not _blob:
                logger.warning(
                    "OutFitDyeSave: player=%s 没有装扮 %s", session.player_id, req.outfit_id
                )
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.OutFitDyeSaveRsp, rsp, packet_id)
                return
            outfit = ItemDetail()
            outfit.ParseFromString(_blob)
            # 染色方案槽位可能还没解锁(列表更短), 原来直接下标取会 IndexError。
            while len(outfit.main_item.outfit.dye_schemes) <= req.scheme_index:
                _s = outfit.main_item.outfit.dye_schemes.add()
                _s.scheme_index = len(outfit.main_item.outfit.dye_schemes) - 1
                _s.is_un_lock = True
            outfit.main_item.outfit.dye_schemes[req.scheme_index].is_un_lock = True
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
        logger.info(
            "OutFitDyeSave: player=%s outfit=%s scheme=%s pos=%s save=%s status=%s color=(%s,%s,%s)",
            session.player_id,
            req.outfit_id,
            req.scheme_index,
            req.pos,
            req.is_save_dye_result,
            rsp.status,
            session.color_data[2].red,
            session.color_data[2].green,
            session.color_data[2].blue,
        )
        trace("dye_save", player=session.player_id, outfit=req.outfit_id, scheme=req.scheme_index,
              pos=req.pos, save=req.is_save_dye_result, status=rsp.status,
              rgb=(session.color_data[2].red, session.color_data[2].green, session.color_data[2].blue))
        session.send(MsgId.OutFitDyeSaveRsp, rsp, packet_id)
        if pack is not None:
            pack.items.add().CopyFrom(outfit)
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
