import numpy as np


def char_pack(x, y):
    """将两个char_id(_0_00_)压缩到一个int32里"""
    a, b, c = x // 100000, (x // 1000) % 10, x % 10
    d, e, f = y // 100000, (y // 1000) % 10, y % 10
    return a | (b << 4) | (c << 8) | (d << 12) | (e << 16) | (f << 20)


def char_unpack(v):
    """char_pack的逆向操作"""
    a = v & 0xF
    b = (v >> 4) & 0xF
    c = (v >> 8) & 0xF
    d = (v >> 12) & 0xF
    e = (v >> 16) & 0xF
    f = (v >> 20) & 0xF
    x = a * 100000 + b * 1000 + c
    y = d * 100000 + e * 1000 + f
    return [x, y]


class SwirlNoiseGenHelper:
    def __init__(self):
        self._swirl_params = None
        self._rotate_coef = 5.0  # field +14: angle = rotate_coef * |z|
        self._radius_coef = 0.5  # field +15: radius = radius_coef * w
        # ColorPower 的指数随 uv_y 在两端之间插值 (field +12 / +13):
        #   exp = (power_y1 - power_y0) * clamp(uv_y, 0, 1) + power_y0
        self._color_power_y1 = 0.2  # uv_y == 1 时的指数
        self._color_power_y0 = 1.5  # uv_y == 0 时的指数
        self._source_texture = None

    def set_swirl_params(self, swirl_params, texture):
        arr = np.array(swirl_params, dtype=np.float64)
        if arr.size != 64:
            return
        self._swirl_params = arr.reshape(16, 4).copy()
        arr = np.array(texture).astype(np.uint8)
        self._source_texture = arr
        self._source_height, self._source_width = arr.shape[:2]

    def _swirl(self, u, v, cx, cy, angle, radius, sign):
        """
        绕 (cx, cy) 做一次衰减旋转。
        radius <= 0 时 blend 恒为 1, final_angle == 0, 即该项为空操作
        (原版对负 radius 的行为)。
        """
        f = np.float32
        ox = u - cx
        oy = v - cy
        # Vector2.magnitude: 点积用 float32, sqrt 走 float64 再回到 float32
        dist = np.sqrt((ox * ox + oy * oy).astype(np.float64)).astype(f)
        rot = angle * np.exp((-dist / radius).astype(f))
        blend = np.clip(np.minimum(dist, radius) / radius, f(0.0), f(1.0))
        final = ((f(0.0) - rot) * blend + rot) * sign
        cos_a = np.cos(final).astype(f)
        sin_a = np.sin(final).astype(f)
        return (ox * cos_a - sin_a * oy + cx).astype(f), (
            ox * sin_a + oy * cos_a + cy
        ).astype(f)

    def get_color_array(self, uv_y, output_color_count):
        if self._swirl_params is None or self._source_texture is None:
            return [(0, 0, 0, 255)] * output_color_count
        f = np.float32
        n = int(output_color_count)
        # GetColor: 第 i 个采样点 u = (i + 1) / (count + 1), v = uv_y
        u = (np.arange(1, n + 1, dtype=f) / f(n + 1.0)).astype(f)
        v = np.full(n, f(uv_y), dtype=f)
        # CalcColor: 依次叠加 16 个 swirl
        rc = f(self._rotate_coef)
        dc = f(self._radius_coef)
        for cx, cy, z, w in self._swirl_params:
            cx, cy, z, w = f(cx), f(cy), f(z), f(w)
            angle = f(abs(z)) * rc
            radius = w * dc
            sign = f(1.0) if z >= 0 else f(-1.0)
            u, v = self._swirl(u, v, cx, cy, angle, radius, sign)
        # UVToPixel: 取小数部分 -> 乘尺寸 -> floor -> clamp。
        # Unity Texture2D.GetPixel 以左下角为原点, 故行号需翻转。
        h, wd = self._source_height, self._source_width
        px = np.clip(np.floor(f(wd) * (u - np.floor(u))).astype(np.int64), 0, wd - 1)
        py = np.clip(np.floor(f(h) * (v - np.floor(v))).astype(np.int64), 0, h - 1)
        texel = self._source_texture[(h - 1) - py, px].astype(f) / f(255.0)
        # ColorPower: 每个 RGB 通道做 channel ** exp
        t = f(min(max(float(uv_y), 0.0), 1.0))
        exp = (f(self._color_power_y1) - f(self._color_power_y0)) * t + f(
            self._color_power_y0
        )
        rgb = np.power(texel[:, :3], exp)
        colors = []
        for i in range(n):
            colors.append(
                (
                    int(round(float(rgb[i, 0]) * 255.0)),
                    int(round(float(rgb[i, 1]) * 255.0)),
                    int(round(float(rgb[i, 2]) * 255.0)),
                    int(round(float(texel[i, 3]) * 255.0)),
                )
            )
        return colors
