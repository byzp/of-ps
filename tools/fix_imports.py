import os
import re


def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()

    # 更通用地匹配： import proto.<module>_pb2 as <alias>
    import_pattern = re.compile(
        r"^\s*import\s+proto\.(\w+_pb2)\s+as\s+(\w+)\s*$", re.MULTILINE
    )

    matched_indices = []
    modules_and_aliases = []  # list of (module_name, alias)
    for i, line in enumerate(lines):
        m = import_pattern.match(line)
        if m:
            module_name, alias = m.group(1), m.group(2)
            matched_indices.append(i)
            modules_and_aliases.append((module_name, alias))

    if not matched_indices:
        return  # 没有匹配到需要替换的 import，跳过

    # 生成别名列表（去掉 _pb2 后缀优先根据 alias）
    aliases_for_import = []
    for module_name, alias in modules_and_aliases:
        if alias.endswith("_pb2"):
            base_name = alias[:-4]
        elif module_name.endswith("_pb2"):
            base_name = module_name[:-4]
        else:
            base_name = alias
        aliases_for_import.append(base_name)

    import_line = f"from proto.net_pb2 import {','.join(aliases_for_import)}"

    # 构造删除了原有匹配 import 后的新行列表
    new_lines = []
    for i, line in enumerate(lines):
        if i in matched_indices:
            continue
        new_lines.append(line)

    # 计算应该插入的位置：原来最后一个匹配行的索引在删除后对应的位置
    # 插入位置 = last_index - (number_of_removed_before_last)
    last_index = matched_indices[-1]
    removed_before_last = sum(1 for idx in matched_indices if idx < last_index)
    insert_idx = last_index - removed_before_last
    if insert_idx < 0:
        insert_idx = 0
    if insert_idx > len(new_lines):
        insert_idx = len(new_lines)

    # 在计算出的插入位置插入新的 import 行
    new_lines.insert(insert_idx, import_line)

    new_content = "\n".join(new_lines)

    # 替换代码中使用类的地方
    # 对每个匹配到的 (module_name, alias) 做替换
    for module_name, alias in modules_and_aliases:
        # 计算 base_name（优先用 alias 去掉 _pb2，否则用 module 去掉）
        if alias.endswith("_pb2"):
            base_name = alias[:-4]
        elif module_name.endswith("_pb2"):
            base_name = module_name[:-4]
        else:
            base_name = alias

        # 1) 替换 alias.BaseName() -> BaseName()
        # 注意：先替换带括号的构造调用，避免部分被下一条通用替换吞掉
        pattern_ctor = re.compile(rf"\b{re.escape(alias)}\.{re.escape(base_name)}\(\)")
        new_content = pattern_ctor.sub(f"{base_name}()", new_content)

        # 2) 替换 alias.BaseName (静态引用) -> BaseName
        pattern_static = re.compile(rf"\b{re.escape(alias)}\.{re.escape(base_name)}\b")
        new_content = pattern_static.sub(base_name, new_content)

        # 3) 替换 alias.SOMETHING -> BaseName.SOMETHING （处理 enum 或其他常量）
        # 为避免把刚替换出的 BaseName.SOMETHING 再次误替换，不要加多余贪婪项
        pattern_other = re.compile(rf"\b{re.escape(alias)}\.(\w+)\b")
        new_content = pattern_other.sub(rf"{base_name}.\1", new_content)

    # 将新内容写回文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Processed: {filepath}")
    print(
        f"  Removed {len(matched_indices)} original import(s), inserted: {import_line}"
    )


# 处理当前目录下的 .py 文件（排除 __init__ 和 本脚本）
for filename in os.listdir("."):
    if (
        filename.endswith(".py")
        and filename != "__init__.py"
        and filename != "fix_imports.py"
    ):
        process_file(filename)
