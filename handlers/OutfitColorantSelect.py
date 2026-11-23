import utils.db as _db

from proto.net_pb2 import ItemDetail as _ID

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import numpy as np
import random

from proto.net_pb2 import OutfitColorantSelectReq, OutfitColorantSelectRsp, StatusCode
from utils.res_loader import res
from utils.algo import SwirlNoiseGenHelper


def ensure_swirl(session):
    """初始化染色 swirl 参数(未选染剂时惰性生成)"""

    if session.color_data[0]:
        return
    p = np.random.rand(16, 4).astype(np.float64) * 0.6 + 0.2
    signs = np.where(np.random.rand(16) > 0.5, 1.0, -1.0)
    p[:, 3] *= signs
    noise_texture_id = random.randint(1, 4)
    session.color_data[1] = noise_texture_id
    helper = SwirlNoiseGenHelper()
    helper.set_swirl_params(p, res[f"{noise_texture_id}.png"])
    session.color_data[0] = helper


@packet_handler(MsgId.OutfitColorantSelectReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitColorantSelectReq()
        req.ParseFromString(data)

        rsp = OutfitColorantSelectRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.param.uvy = 0.0
        rsp.param.is_dye = False

        # 选择染剂: 必须在 DyeStuff.dye_data 配置内且背包拥有

        _stuffs = {
            d["i_d"]
            for d in res.get("DyeStuff", {}).get("dye_data", {}).get("datas", [])
            if isinstance(d, dict)
        }
        if req.colorant_item_id and _stuffs and (req.colorant_item_id not in _stuffs):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.OutfitColorantSelectRsp, rsp, packet_id)
            return
        if req.colorant_item_id:
            blob = _db.get_item_detail(session.player_id, req.colorant_item_id)
            have = False
            if blob and isinstance(blob, (bytes, bytearray)):

                d = _ID()
                d.ParseFromString(blob)
                have = d.main_item.base_item.num > 0
            if not have:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.OutfitColorantSelectRsp, rsp, packet_id)
                return
        _db.set_kv(
            session.player_id,
            "outfit_dye",
            "selected_colorant",
            int(req.colorant_item_id or 0),
        )

        ensure_swirl(session)
        rsp.param.picture_id = session.color_data[1]
        rsp.param.params.extend(
            session.color_data[0]._swirl_params.copy().reshape(64).tolist()
        )
        session.send(MsgId.OutfitColorantSelectRsp, rsp, packet_id)
