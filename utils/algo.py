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
