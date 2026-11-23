"""只读解析抓包，按消息汇总所有样本的字段形状和请求值，不访问玩家数据库。"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from google.protobuf import text_format

from proto import net_pb2


def shape(message):
    fields = []
    for descriptor, value in message.ListFields():
        name = descriptor.name
        if descriptor.message_type is not None:
            if descriptor.message_type.GetOptions().map_entry:
                fields.append(f"{name}[map]")
            elif descriptor.is_repeated:
                children = sorted({shape(child) for child in value})
                fields.append(f"{name}[{'|'.join(children)}]")
            else:
                fields.append(f"{name}{{{shape(value)}}}")
        else:
            fields.append(name)
    return ",".join(fields)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    groups = defaultdict(list)
    for path in sorted(
        args.directory.glob("*.txt"), key=lambda p: float(p.name.split("-")[0])
    ):
        name = path.name.split("-")[1]
        message = text_format.Parse(
            path.read_text(encoding="utf-8-sig"), getattr(net_pb2, name)()
        )
        groups[name].append((path.name, message))
    print(f"已完整解析 {sum(map(len, groups.values()))} 个包，{len(groups)} 种消息。")
    for name, entries in sorted(groups.items()):
        if args.names and name not in args.names:
            continue
        print(f"\n{name}: {len(entries)}")
        for form, count in Counter(shape(message) for _, message in entries).items():
            print(f"  {count}x {form}")
        if name.endswith("Req") and name not in (
            "VerifyLoginTokenReq",
            "PlayerLoginReq",
        ):
            for value, count in Counter(
                text_format.MessageToString(message, as_one_line=True)
                for _, message in entries
            ).items():
                print(f"  请求 {count}x {value}")
        if entries and hasattr(entries[0][1], "status"):
            print("  状态", dict(Counter(message.status for _, message in entries)))


if __name__ == "__main__":
    main()
