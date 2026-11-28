import logging

import utils.db as _db

from proto.net_pb2 import ItemDetail as _ID
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import numpy as np
import random

from proto.net_pb2 import OutfitColorantSelectReq, OutfitColorantSelectRsp, StatusCode
from utils.res_loader import res
from utils.trace import trace
from utils.algo import SwirlNoiseGenHelper
from server import character_growth as growth

logger = logging.getLogger(__name__)


def ensure_swirl(session):
    """初始化染色 swirl 参数(未选染剂时惰性生成)。"""
    if session.color_data[0]:
        return
    params = np.random.rand(16, 4).astype(np.float64) * 0.6 + 0.2
    signs = np.where(np.random.rand(16) > 0.5, 1.0, -1.0)
    params[:, 3] *= signs
    noise_texture_id = random.randint(1, 4)
    session.color_data[1] = noise_texture_id
    helper = SwirlNoiseGenHelper()
    helper.set_swirl_params(params, res[f"{noise_texture_id}.png"])
    session.color_data[0] = helper


@packet_handler(MsgId.OutfitColorantSelectReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitColorantSelectReq()
        req.ParseFromString(data)
        rsp = OutfitColorantSelectRsp(status=StatusCode.StatusCode_OK)
        rsp.param.uvy = 0.0
        rsp.param.is_dye = False
        try:
            with growth.transaction(session.player_id):
                if req.outfit_id:
                    growth.load_owned_outfit(session.player_id, req.outfit_id)
                if req.colorant_item_id:
                    cfg = growth.item_config(req.colorant_item_id)
                    configured = any(
                        row.get("i_d") == req.colorant_item_id
                        for row in growth.rows("DyeStuff", "dye_data")
                    )
                    if cfg is None or cfg.get("new_bag_item_tag") != 26 or not configured:
                        raise growth.GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
                    blob = _db.get_item_detail(session.player_id, req.colorant_item_id)
                    if not blob:
                        raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                    detail = _ID()
                    detail.ParseFromString(blob)
                    if (
                        detail.main_item.WhichOneof("item") != "base_item"
                        or detail.main_item.item_id != req.colorant_item_id
                        or detail.main_item.base_item.num <= 0
                    ):
                        raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                _db.set_kv(
                    session.player_id,
                    "outfit_dye",
                    "selected_colorant",
                    int(req.colorant_item_id or 0),
                )
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.OutfitColorantSelectRsp, rsp, packet_id)
            return

        ensure_swirl(session)
        rsp.param.picture_id = session.color_data[1]
        rsp.param.params.extend(
            session.color_data[0]._swirl_params.copy().reshape(64).tolist()
        )
        logger.info(
            "OutfitColorantSelect: player=%s colorant=%s status=%s picture_id=%s",
            session.player_id,
            req.colorant_item_id,
            rsp.status,
            rsp.param.picture_id,
        )
        trace("colorant", player=session.player_id, colorant=req.colorant_item_id,
              status=rsp.status, pic=rsp.param.picture_id)
        session.send(MsgId.OutfitColorantSelectRsp, rsp, packet_id)
