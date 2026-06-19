from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import numpy as np
import random

from proto.net_pb2 import OutfitColorantSelectReq, OutfitColorantSelectRsp, StatusCode
from utils.res_loader import res
from utils.algo import SwirlNoiseGenHelper


@packet_handler(MsgId.OutfitColorantSelectReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitColorantSelectReq()
        req.ParseFromString(data)

        rsp = OutfitColorantSelectRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.param.uvy = 0.0
        rsp.param.is_dye = False

        if not session.color_data[0]:
            p = np.random.rand(16, 4).astype(np.float64) * 0.6 + 0.2
            signs = np.where(np.random.rand(16) > 0.5, 1.0, -1.0)
            p[:, 3] *= signs
            swirl_params = p
            noise_texture_id = random.randint(1, 4)
            session.color_data[1] = noise_texture_id

            helper = SwirlNoiseGenHelper()
            helper.set_swirl_params(swirl_params, res[f"{noise_texture_id}.png"])
            session.color_data[0] = helper
        rsp.param.picture_id = session.color_data[1]
        rsp.param.params.extend(
            session.color_data[0]._swirl_params.copy().reshape(64).tolist()
        )
        session.send(MsgId.OutfitColorantSelectRsp, rsp, packet_id)
