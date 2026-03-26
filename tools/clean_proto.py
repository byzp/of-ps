#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
clean_proto.py

用法：
    python clean_proto.py --py msg_id.py --proto input.proto --out output.proto

默认：
    从 py 文件里的 class MsgId: 提取字段名
    仅保留 proto 中同名 message/enum/service，并递归保留依赖消息
    enum 统一放在前面
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple


SCALAR_TYPES = {
    "double",
    "float",
    "int32",
    "int64",
    "uint32",
    "uint64",
    "sint32",
    "sint64",
    "fixed32",
    "fixed64",
    "sfixed32",
    "sfixed64",
    "bool",
    "string",
    "bytes",
}


@dataclass
class ProtoBlock:
    kind: str  # message / enum / service / ...
    name: str
    text: str  # 整个块文本（包含外层大括号）
    body: str  # 去掉外层大括号后的内容
    start: int
    end: int  # 结束下标（包含）


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def extract_msgid_names(py_text: str, class_name: str = "MsgId") -> Set[str]:
    """
    从 python 文件里提取 class MsgId: 下的字段名。
    例如：
        class MsgId:
            InValid = -1
            VerifyLoginTokenReq = 1001
    """
    # 找到 class MsgId: 到下一个 class 或文件结束
    m = re.search(
        rf"(?ms)^\s*class\s+{re.escape(class_name)}\s*:\s*(.*?)(?=^\s*class\s+\w+\s*:|\Z)",
        py_text,
    )
    if not m:
        return set()

    body = m.group(1)
    names = set(re.findall(r"(?m)^\s*([A-Za-z_]\w*)\s*=", body))
    return names


def find_matching_brace(text: str, open_brace_idx: int) -> int:
    """
    从 open_brace_idx 开始，找到对应的 '}'。
    会尽量跳过 // 注释、/* */ 注释、字符串。
    """
    assert text[open_brace_idx] == "{"

    i = open_brace_idx
    depth = 0
    in_line_comment = False
    in_block_comment = False
    in_string = False
    escape = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    raise ValueError(f"未找到匹配的大括号，起始位置：{open_brace_idx}")


def parse_top_level_blocks(text: str) -> Tuple[List[ProtoBlock], List[Tuple[int, int]]]:
    """
    解析 proto 顶层块：
      message XXX { ... }
      enum XXX { ... }
      service XXX { ... }

    返回：
      blocks: 解析出的块
      spans : 每个块的 [start, end]，用于后续从原文中移除这些块
    """
    blocks: List[ProtoBlock] = []
    spans: List[Tuple[int, int]] = []

    i = 0
    n = len(text)
    depth = 0
    in_line_comment = False
    in_block_comment = False
    in_string = False
    escape = False

    # 仅解析这些顶层块；你也可以按需加 extend / oneof 等
    block_kw_re = re.compile(r"[ \t]*(message|enum|service)\s+([A-Za-z_]\w*)\s*\{")

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        # 只在顶层识别块
        if depth == 0:
            m = block_kw_re.match(text, i)
            if m:
                kind = m.group(1)
                name = m.group(2)
                block_start = (
                    i + len(text[i : m.end()]) - len(text[i : m.end()].lstrip())
                )
                # 上面这句是为了包含前导空白；更简单的做法是直接从 i 开始切
                block_start = i

                open_brace_idx = text.find("{", m.start(), m.end())
                if open_brace_idx == -1:
                    raise ValueError(f"无法找到块的 '{{'：{kind} {name}")

                close_brace_idx = find_matching_brace(text, open_brace_idx)
                block_end = close_brace_idx

                full_text = text[block_start : block_end + 1]
                body = text[open_brace_idx + 1 : block_end]

                blocks.append(
                    ProtoBlock(
                        kind=kind,
                        name=name,
                        text=full_text,
                        body=body,
                        start=block_start,
                        end=block_end,
                    )
                )
                spans.append((block_start, block_end + 1))
                i = block_end + 1
                continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)

        i += 1

    return blocks, spans


def extract_non_block_text(text: str, spans: List[Tuple[int, int]]) -> str:
    """
    把所有顶层块从原文里剥离，保留其余文本。
    """
    if not spans:
        return text

    spans = sorted(spans, key=lambda x: x[0])
    parts = []
    last = 0
    for s, e in spans:
        if last < s:
            parts.append(text[last:s])
        last = max(last, e)
    if last < len(text):
        parts.append(text[last:])
    return "".join(parts)


def split_map_type(type_text: str) -> Tuple[str, str]:
    """
    map<key, value> -> (key, value)
    """
    inner = type_text.strip()[4:-1]  # 去掉 map< 和 >
    left, right = inner.split(",", 1)
    return left.strip(), right.strip()


def candidate_type_names(type_name: str) -> List[str]:
    """
    从字段类型中提取可能对应的 proto 定义名。
    例如：
      Foo            -> ["Foo"]
      Outer.Inner    -> ["Outer", "Inner"]
      a.b.c.TypeName -> ["a", "b", "c", "TypeName"]

    这样做是为了兼容：
      - 顶层 message / enum
      - 简单嵌套类型引用
    """
    parts = [p for p in type_name.split(".") if p]
    if not parts:
        return []
    # 去重但保序
    out = []
    seen = set()
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    if parts[-1] not in seen:
        out.append(parts[-1])
    return out


def extract_references_from_message_body(body: str) -> Set[str]:
    """
    从 message body 中提取引用到的类型名。
    这里用的是常见字段声明的正则，足够覆盖大多数 proto。
    """
    refs: Set[str] = set()

    # 常见字段声明：
    #   repeated Foo bar = 1;
    #   optional Foo bar = 1;
    #   map<string, Foo> bar = 1;
    #   Foo bar = 1;
    #
    # oneof 里的字段也通常能被捕获。
    field_re = re.compile(
        r"(?m)^\s*(?:repeated|optional|required)?\s*"
        r"(map<[^>]+>|[A-Za-z_][\w\.]*)\s+"
        r"[A-Za-z_]\w*\s*=\s*\d+\s*(?:\[[^\]]*\]\s*)?;"
    )

    for m in field_re.finditer(body):
        raw_type = m.group(1).strip()

        if raw_type.startswith("map<") and raw_type.endswith(">"):
            _, value_type = split_map_type(raw_type)
            for c in candidate_type_names(value_type):
                refs.add(c)
        else:
            for c in candidate_type_names(raw_type):
                refs.add(c)

    # 去掉基础类型
    refs = {r for r in refs if r not in SCALAR_TYPES}
    return refs


def clean_proto(py_text: str, proto_text: str, class_name: str = "MsgId") -> str:
    target_names = extract_msgid_names(py_text, class_name=class_name)

    blocks, spans = parse_top_level_blocks(proto_text)
    non_block_text = extract_non_block_text(proto_text, spans)

    # 建立 name -> block 映射
    block_map: Dict[str, ProtoBlock] = {}
    ordered_blocks: List[ProtoBlock] = []
    for b in blocks:
        # 只保留第一次出现的同名定义
        if b.name not in block_map:
            block_map[b.name] = b
            ordered_blocks.append(b)

    # 以 py 的字段名作为初始保留集合
    keep: Set[str] = set(name for name in target_names if name in block_map)

    # 递归保留依赖消息/枚举
    queue = list(keep)
    while queue:
        name = queue.pop()
        blk = block_map.get(name)
        if not blk:
            continue

        # service 不做依赖递归；enum 也不用递归
        if blk.kind != "message":
            continue

        refs = extract_references_from_message_body(blk.body)
        for ref in refs:
            if ref in block_map and ref not in keep:
                keep.add(ref)
                queue.append(ref)

    # 分类输出：enum 前置，再 message，再 service
    kept_enums = [b.text for b in ordered_blocks if b.kind == "enum" and b.name in keep]
    kept_messages = [
        b.text for b in ordered_blocks if b.kind == "message" and b.name in keep
    ]
    kept_services = [
        b.text for b in ordered_blocks if b.kind == "service" and b.name in keep
    ]

    # 头部文本（syntax/package/import/option/注释等非块内容）
    header = non_block_text.rstrip()

    output_parts = []
    if header:
        output_parts.append(header)

    def append_section(items: List[str]) -> None:
        if not items:
            return
        if output_parts:
            output_parts.append("")
        output_parts.append("\n\n".join(s.rstrip() for s in items))

    append_section(kept_enums)
    append_section(kept_messages)
    append_section(kept_services)

    result = "\n".join(output_parts).rstrip() + "\n"
    return result


def format_proto_indentation(text: str, indent: str = "    ") -> str:
    """
    将 proto 文本按大括号层级重排为 4 空格缩进。
    这是一个实用型格式化，不是完整的 proto parser。
    """
    lines = text.splitlines()
    out = []
    level = 0

    in_block_comment = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            out.append("")
            continue

        # 处理块注释起止
        if in_block_comment:
            out.append(indent * level + stripped)
            if "*/" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("/*") and "*/" not in stripped:
            out.append(indent * level + stripped)
            in_block_comment = True
            continue

        # 先判断这一行是否以 } 开头，需要先减层级
        leading_close = 0
        i = 0
        while i < len(stripped) and stripped[i] == "}":
            leading_close += 1
            i += 1

        current_level = max(level - leading_close, 0)
        out.append(indent * current_level + stripped)

        # 再根据本行的 { 和 } 更新层级
        # 这里做一个简单统计，足够覆盖大多数 proto
        open_count = stripped.count("{")
        close_count = stripped.count("}")
        level = max(level + open_count - close_count, 0)

    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="根据 py 中的 MsgId 字段名清洗 proto。"
    )
    parser.add_argument("--py", required=True, help="包含 MsgId 的 Python 文件路径")
    parser.add_argument("--proto", required=True, help="需要清洗的 proto 文件路径")
    parser.add_argument("--out", required=True, help="输出 proto 文件路径")
    parser.add_argument(
        "--class-name", default="MsgId", help="Python 里的类名，默认 MsgId"
    )

    args = parser.parse_args()

    py_text = read_text(args.py)
    proto_text = read_text(args.proto)

    cleaned = clean_proto(py_text, proto_text, class_name=args.class_name)
    cleaned = format_proto_indentation(cleaned, indent="    ")
    write_text(args.out, cleaned)

    print(f"done: {args.out}")


if __name__ == "__main__":
    main()
