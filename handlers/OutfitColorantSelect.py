from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import numpy as np
import random

import proto.OverField_pb2 as OutfitColorantSelectReq_pb2
import proto.OverField_pb2 as OutfitColorantSelectRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutfitColorantSelectReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitColorantSelectReq_pb2.OutfitColorantSelectReq()
        req.ParseFromString(data)

        rsp = OutfitColorantSelectRsp_pb2.OutfitColorantSelectRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.param.uvy = 0.0
        rsp.param.is_dye = False

        if not session.color_data[0]:
            p = np.random.rand(16, 4).astype(np.float64) * 0.6 + 0.2
            signs = np.where(np.random.rand(16) > 0.5, 1.0, -1.0)
            p[:, 3] *= signs
            swirl_params = p
            noise_texture_id = random.randint(1, 4)
            session.color_data[1] = noise_texture_id

            helper = SwirlNoiseGenHelper()  # TODO 颜色仅大致正确 也许是
            helper.set_swirl_params(swirl_params, res[f"{noise_texture_id}.png"])
            session.color_data[0] = helper
        rsp.param.picture_id = session.color_data[1]
        rsp.param.params.extend(
            session.color_data[0]._swirl_params.copy().reshape(64).tolist()
        )
        session.send(MsgId.OutfitColorantSelectRsp, rsp, packet_id)


class SwirlNoiseGenHelper:
    def __init__(self):
        self._swirl_params = None
        self._rotate_coef = 5.0
        self._radius_coef = 0.5
        self._source_texture = None

    def set_swirl_params(self, swirl_params, texture):
        arr = np.array(swirl_params, dtype=np.float64)
        if arr.size != 64:
            return
        self._swirl_params = arr.reshape(16, 4).copy()
        arr = np.array(texture).astype(np.uint8)
        self._source_texture = arr
        self._source_height, self._source_width = arr.shape[:2]

    def _nearest_sample(self, texture, u, v):
        h, w = texture.shape[:2]
        x = np.floor(u * w).astype(int) % w
        y = np.floor(v * h).astype(int) % h
        res = texture[y, x]
        return res

    def get_color_array(self, uv_y, output_color_count):
        uv_y = 1 - uv_y
        u = (
            np.arange(1, output_color_count + 1, dtype=np.float64)
            / (output_color_count + 1.0)
        ).astype(np.float64)
        v = np.full_like(u, uv_y, dtype=np.float64)
        u = u % 1.0
        v = v % 1.0
        u_grid = u
        v_grid = v
        inv_v = 1.0 - v_grid
        u_curr = u_grid.copy()
        for i in range(self._swirl_params.shape[0]):
            cx = float(self._swirl_params[i, 0])
            cy = float(self._swirl_params[i, 1])
            z = float(self._swirl_params[i, 2])
            w = float(self._swirl_params[i, 3])
            ox = u_curr - cx
            oy = inv_v - cy
            dist = np.hypot(ox, oy)
            angle = self._rotate_coef * abs(z)
            radius = self._radius_coef * w
            radius_safe = np.where(radius <= 0.0, 1e-9, radius)
            decay = np.exp(-dist / radius_safe)
            decay = 0.0 if radius <= 0.0 else decay
            rotation_amount = angle * decay
            min_dist = np.minimum(dist, radius_safe)
            blend = 1.0 if radius <= 0.0 else (min_dist / radius_safe)
            final_angle = rotation_amount * (1.0 - blend)
            direction = np.sign(z) if z != 0 else 1.0
            final_angle = final_angle * direction
            cos_a = np.cos(final_angle)
            sin_a = np.sin(final_angle)
            rx = ox * cos_a - oy * sin_a
            ry = ox * sin_a + oy * cos_a
            u_curr = rx + cx
            inv_v = ry + cy
        v_final = 1.0 - inv_v
        u_final = np.mod(u_curr, 1.0)
        v_final = np.mod(v_final, 1.0)
        if self._source_texture is None:
            return [(0.0, 0.0, 0.0, 1.0)] * output_color_count
        sampled = self._nearest_sample(self._source_texture, u_final, v_final)
        colors = []
        for i in range(output_color_count):
            px = sampled[i]
            r = int(px[0])
            g = int(px[1])
            b = int(px[2])
            a = int(px[3])
            colors.append((r, g, b, a))
        return colors
