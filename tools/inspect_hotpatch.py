"""只读检查 UnityFS 内 InjectFix 补丁的指令和外部引用。"""

import argparse
import io
from pathlib import Path
import struct

from cramjam import lz4


class Reader(io.BytesIO):
    def integer(self):
        return struct.unpack("<i", self.read(4))[0]

    def boolean(self):
        return self.read(1) != b"\0"

    def string(self):
        length = shift = 0
        while True:
            value = self.read(1)[0]
            length |= (value & 127) << shift
            if value < 128:
                break
            shift += 7
        return self.read(length).decode("utf-8")


def unpack_bundle(path):
    data = path.read_bytes()
    stream = io.BytesIO(data)
    for index in range(3):
        while stream.read(1) != b"\0":
            pass
        if index == 0:
            stream.read(4)
    _, compressed, size, flags = struct.unpack(">QIII", stream.read(20))
    offset = (stream.tell() + 15) // 16 * 16
    info = bytes(
        lz4.decompress_block(data[offset : offset + compressed], output_len=size)
    )
    table = io.BytesIO(info)
    table.read(16)
    blocks = [
        struct.unpack(">IIH", table.read(10))
        for _ in range(struct.unpack(">I", table.read(4))[0])
    ]
    offset += compressed
    if flags & 0x200:
        offset = (offset + 15) // 16 * 16
    result = bytearray()
    for size, compressed, mode in blocks:
        block = data[offset : offset + compressed]
        offset += compressed
        result.extend(
            bytes(lz4.decompress_block(block, output_len=size))
            if mode & 63 in (2, 3)
            else block
        )
    return bytes(result)


def inspect(path):
    data = unpack_bundle(path)
    start = data.index(b"IFix.ILFixInterfaceBridge") - 1
    stream = Reader(data[start:])
    print("bridge:", stream.string())
    types = [stream.string() for _ in range(stream.integer())]
    methods = []
    for _ in range(stream.integer()):
        methods.append(
            [struct.unpack("<ii", stream.read(8)) for _ in range(stream.integer())]
        )
        stream.read(stream.integer() * 24)

    def method():
        generic = stream.boolean()
        owner = types[stream.integer()].split(",")[0]
        name = stream.string()
        if generic:
            for _ in range(stream.integer()):
                stream.integer()
            params = [
                stream.string() if stream.boolean() else types[stream.integer()]
                for _ in range(stream.integer())
            ]
        else:
            params = [types[stream.integer()] for _ in range(stream.integer())]
        return (
            owner + "." + name + "(" + ",".join(p.split(",")[0] for p in params) + ")"
        )

    externs = [method() for _ in range(stream.integer())]
    strings = [stream.string() for _ in range(stream.integer())]
    fields = []
    for _ in range(stream.integer()):
        new = stream.boolean()
        owner = types[stream.integer()].split(",")[0]
        fields.append(owner + "." + stream.string())
        if new:
            stream.read(8)
    for name, values in (("extern", externs), ("string", strings), ("field", fields)):
        for index, value in enumerate(values):
            print(name, index, value)
    for index, code in enumerate(methods):
        print("METHOD", index, len(code))
        for pc, (op, operand) in enumerate(code):
            print(pc, op, operand)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    inspect(parser.parse_args().bundle)
