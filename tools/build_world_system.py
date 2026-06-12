"""
build_world_system.py

从 String_Simplified.json 的 string_moon_stone_text 中提取所有星云树节点，
按世界 ID 分组（i_d < 1_000_000 取首数字，≥ 1_000_000 取前 4 位），
生成 world_system.json。

输出格式:
{
  "<world_id>": {
    "<node_i_d>": {
      "<description_text>": ""
    },
    ...
  },
  ...
}

使用方法:
  python build_world_system.py [--input <path>] [--output <path>]

默认输入: resources/data/String_Simplified.json
默认输出: resources/data/world_system.json
"""

import json
import argparse
import os


def build(input_path: str, output_path: str) -> None:
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data['string_moon_stone_text']['datas']

    worlds: dict[str, dict[str, dict[str, str]]] = {}

    for item in entries:
        if not isinstance(item, dict) or 'text' not in item:
            continue
        text = item['text']
        if not isinstance(text, list) or len(text) < 4:
            continue
        tag = text[2]
        desc = text[3]
        if not tag or not desc:
            continue

        i_d = item['i_d']
        s = str(i_d)

        # world_id: first digit or first 4 digits for 9-digit IDs
        if i_d >= 1_000_000:
            world_id = s[:4]
        else:
            world_id = s[0]

        worlds.setdefault(world_id, {})[s] = {desc: ""}

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(worlds, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in worlds.values())
    print(f"Done. {total} entries, {len(worlds)} worlds.")
    for wid in sorted(worlds, key=lambda x: (len(x), x)):
        print(f"  World {wid}: {len(worlds[wid])} entries")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build world-grouped system data from String_Simplified.json")
    default_input = os.path.join(os.path.dirname(__file__), '..', 'resources', 'data', 'String_Simplified.json')
    default_output = os.path.join(os.path.dirname(__file__), '..', 'resources', 'data', 'world_system.json')
    parser.add_argument('--input', default=os.path.normpath(default_input), help='Input JSON path')
    parser.add_argument('--output', default=os.path.normpath(default_output), help='Output JSON path')
    args = parser.parse_args()
    build(args.input, args.output)
