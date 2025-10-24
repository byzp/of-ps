#!/usr/bin/env python3
"""
bytes_to_json.py

说明:
- 先运行:
    protoc --descriptor_set_out=net.desc --include_imports net.proto
  然后运行本脚本（与 net.desc 同目录或用 --desc 指定路径）。
- 默认映射规则: "ActivityGift.bytes" -> message name "AllActivityGiftDatas"
  (即: "All" + <FileStem> + "Datas")。如果规则不适用，可在 mapping.json 指定显式映射。

用法:
    python bytes_to_json.py \
        --desc net.desc \
        --indir ./bytes_files \
        --outdir ./out \
        [--mapping mapping.json]
"""

import argparse
import os
import json
from google.protobuf import (
    descriptor_pb2,
    descriptor_pool,
    message_factory,
    json_format,
)


def load_file_descriptor_set(desc_path: str) -> descriptor_pb2.FileDescriptorSet:
    with open(desc_path, "rb") as f:
        data = f.read()
    fds = descriptor_pb2.FileDescriptorSet()
    fds.ParseFromString(data)
    return fds


def build_descriptor_pool(
    fds: descriptor_pb2.FileDescriptorSet,
) -> descriptor_pool.DescriptorPool:
    pool = descriptor_pool.DescriptorPool()
    # Add each FileDescriptorProto into the pool
    for fd_proto in fds.file:
        pool.Add(fd_proto)
    return pool


def infer_message_name_from_filename(stem: str) -> str:
    """
    默认推断规则:
      e.g. ActivityGift -> AllActivityGiftDatas
      e.g. ActivityInvite -> AllActivityInviteDatas
    如果你的命名规则不同，请使用 mapping.json 指定显式映射。
    """
    return f"All{stem}Datas"


def find_descriptor(pool: descriptor_pool.DescriptorPool, full_name_guess: str):
    """
    尝试多种可能：带/不带包前缀。返回 Descriptor 或 None。
    """
    # 1) 直接尝试全名（可能用户提供了带包的名字）
    try:
        return pool.FindMessageTypeByName(full_name_guess)
    except Exception:
        pass

    # 2) 如果 guess 没有包名，尝试在 pool 中搜索带包的匹配（遍历 registered file descriptors）
    # 由于 DescriptorPool 没有列出全部类型名的直接 API，这里尝试读取 file descriptors from pool via workaround:
    # We'll iterate file names from pool via descriptors copied from a FileDescriptorSet input (handled externally).
    # Simpler approach: try common package prefixes (if you know package, you can add them to try list).
    # For now return None to require either explicit mapping or full type name.
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desc", required=True, help="path to descriptor set (net.desc)")
    ap.add_argument(
        "--indir", default=".", help="input directory containing .bytes files"
    )
    ap.add_argument("--outdir", default="./out", help="output directory for json files")
    ap.add_argument(
        "--mapping",
        default=None,
        help='optional json file mapping filenames to message names. Example: {"ActivityGift.bytes":"MyPackage.AllActivityGiftDatas"}',
    )
    ap.add_argument(
        "--try-prefixes",
        nargs="*",
        default=None,
        help="optional list of package prefixes to try (e.g. GameProto, gameproto). If guessing fails script will attempt these as 'prefix.MessageName'.",
    )
    args = ap.parse_args()

    # load mapping if present
    mapping = {}
    if args.mapping:
        with open(args.mapping, "r", encoding="utf-8") as mf:
            mapping = json.load(mf)

    # load descriptor set and build pool
    fds = load_file_descriptor_set(args.desc)
    pool = descriptor_pool.DescriptorPool()
    # add file descriptors to pool (need FileDescriptorProto)
    for fd_proto in fds.file:
        pool.Add(fd_proto)

    # Build a helper dict of all message full names available (for searching)
    available_message_fullnames = set()
    for fd in fds.file:
        pkg = fd.package or ""
        for msg in fd.message_type:
            # top-level messages only; for nested messages we should walk recursively
            def collect_message(prefix, msg_proto):
                fullname = f"{prefix}.{msg_proto.name}" if prefix else msg_proto.name
                available_message_fullnames.add(fullname)
                # nested
                for nested in msg_proto.nested_type:
                    collect_message(fullname, nested)

            collect_message(pkg, msg)

    # helper to resolve a message name (supports plain short name or full name)
    def resolve_message_descriptor(name_hint: str):
        # if exact match (full name) exists in pool
        try:
            desc = pool.FindMessageTypeByName(name_hint)
            return desc
        except Exception:
            pass

        # if name_hint is short (no dot) try pkg + '.' + name for available pkgs
        if "." not in name_hint:
            # try all available fullnames that endwith the short name
            matches = [
                n
                for n in available_message_fullnames
                if n.endswith("." + name_hint) or n == name_hint
            ]
            if len(matches) == 1:
                try:
                    return pool.FindMessageTypeByName(matches[0])
                except Exception:
                    pass
            elif len(matches) > 1:
                print(
                    f"[WARN] multiple message types match '{name_hint}': {matches}. Please provide explicit mapping."
                )
                return None

        # try provided prefixes
        if args.try_prefixes:
            for p in args.try_prefixes:
                candidate = f"{p}.{name_hint}"
                try:
                    desc = pool.FindMessageTypeByName(candidate)
                    return desc
                except Exception:
                    continue

        return None

    os.makedirs(args.outdir, exist_ok=True)

    files = [f for f in os.listdir(args.indir) if f.endswith(".bytes")]
    if not files:
        print("No .bytes files found in", args.indir)
        return

    factory = message_factory.MessageFactory(pool)

    for fname in files:
        fpath = os.path.join(args.indir, fname)
        stem = os.path.splitext(fname)[0]
        # determine message name
        if fname in mapping:
            msgname = mapping[fname]
        else:
            # default inference rule
            inferred = infer_message_name_from_filename(stem)
            msgname = inferred

        desc = resolve_message_descriptor(msgname)
        if desc is None:
            print(f"[ERROR] Can't find descriptor for '{msgname}' (file {fname}).")
            print("  Suggestions:")
            print("   - add explicit mapping in mapping.json")
            print("   - or re-run with --try-prefixes to try package prefixes")
            print("   - Available message names (sample):")
            sample = list(available_message_fullnames)[:30]
            for s in sample:
                print("     ", s)
            continue

        # create message class prototype and parse
        # 兼容不同版本的 protobuf：优先尝试 factory.GetPrototype，若不存在则回退到模块级的 GetMessageClass
        try:
            prototype = factory.GetPrototype(desc)  # 在部分旧版 protobuf 可用
        except AttributeError:
            # 在某些环境下 MessageFactory 没有 GetPrototype，使用模块级的 GetMessageClass 返回具体类
            prototype = message_factory.GetMessageClass(desc)

        m = prototype()
        with open(fpath, "rb") as f:
            raw = f.read()
        try:
            m.ParseFromString(raw)
        except Exception as e:
            print(f"[ERROR] parse failed for {fname} as {msgname}: {e}")
            continue

        # convert to JSON
        # using json_format.MessageToJson yields JSON string; MessageToDict yields dict
        # -----------------------
        # convert to JSON (兼容不同版本的 protobuf)
        # -----------------------
        try:
            # 尝试使用 MessageToJson（有些新版 protobuf 支持 including_default_value_fields）
            jstr = None
            try:
                # 优先使用带 including_default_value_fields 的形式（漂亮且字段名保留 proto 风格）
                jstr = json_format.MessageToJson(
                    m,
                    preserving_proto_field_name=True,
                    including_default_value_fields=False,  # may not exist in older protobuf
                    indent=2,
                    ensure_ascii=False,
                )
            except TypeError:
                # older protobuf: MessageToJson 不接受 including_default_value_fields
                # 退回到不带该参数的 MessageToJson（若可用）
                try:
                    jstr = json_format.MessageToJson(
                        m,
                        preserving_proto_field_name=True,
                        indent=2,
                        ensure_ascii=False,
                    )
                except TypeError:
                    # 极端兼容路径：把 message 转成 dict 再 json.dumps（可控制是否包含默认字段）
                    d = json_format.MessageToDict(
                        m,
                        preserving_proto_field_name=True,
                        including_default_value_fields=False,  # 如果这个也不支持，再去掉
                    )
                    jstr = json.dumps(d, ensure_ascii=False, indent=2)
        except TypeError:
            # 如果 including_default_value_fields 在 MessageToDict 也不支持（非常旧的版本），退到最基本的调用
            d = json_format.MessageToDict(m, preserving_proto_field_name=True)
            jstr = json.dumps(d, ensure_ascii=False, indent=2)

        outpath = os.path.join(args.outdir, stem + ".json")
        with open(outpath, "w", encoding="utf-8") as fo:
            fo.write(jstr)
        print(f"[OK] {fname} -> {outpath}  (message: {msgname})")

    print("done.")


if __name__ == "__main__":
    main()
