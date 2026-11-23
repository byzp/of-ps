#!/usr/bin/env python3
"""机械校验 handlers/*.py:
1. py_compile 语法
2. import + 注册重复检查 + 装饰器/Rsp id 一致性
3. AST 字段名校验: 变量 -> protobuf Descriptor 数据流追踪, 报告不存在的字段
用法: python3 check_handlers.py [files...]   (默认全部 handlers/*.py)
"""

import ast
import glob
import importlib
import os
import py_compile
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from proto import net_pb2  # noqa: E402
from network.msg_id import MsgId  # noqa: E402

MSG_IDS = {k: v for k, v in vars(MsgId).items() if isinstance(v, int)}

# protobuf Message 上的合法方法/属性, 不当字段处理
MSG_METHODS = {
    "ParseFromString",
    "SerializeToString",
    "SerializePartialToString",
    "CopyFrom",
    "MergeFrom",
    "Clear",
    "ClearField",
    "HasField",
    "WhichOneof",
    "SetInParent",
    "IsInitialized",
    "ListFields",
    "ByteSize",
    "DESCRIPTOR",
    # repeated 容器方法
    "add",
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "sort",
    "MergeFrom",
}

problems = []


def note(f, lineno, msg):
    problems.append(f"{f}:{lineno}: {msg}")


def field_map(desc):
    return {fd.name: fd for fd in desc.fields}


class Checker(ast.NodeVisitor):
    def __init__(self, fname, pb_names):
        self.fname = fname
        self.pb_names = pb_names  # name -> message class (net_pb2 中 import 的)
        self.vars = {}  # var name -> descriptor (message) 或 ('repeated', field_desc)

    # --- helpers -------------------------------------------------------
    def desc_of_expr(self, node):
        """返回表达式对应的 message Descriptor, 未知返回 None; ('repeated', fd) 表示 repeated 容器"""
        if isinstance(node, ast.Name):
            return self.vars.get(node.id)
        if isinstance(node, ast.Call):
            # SomeMsg() / x.add()
            f = node.func
            if isinstance(f, ast.Name) and f.id in self.pb_names:
                return self.pb_names[f.id].DESCRIPTOR
            if isinstance(f, ast.Attribute) and f.attr == "add":
                base = self.desc_of_expr(f.value)
                if isinstance(base, tuple) and base[0] == "repeated":
                    fd = base[1]
                    if fd.message_type:
                        return fd.message_type
                return None
            return None
        if isinstance(node, ast.Attribute):
            base = self.desc_of_expr(node.value)
            if base is None or isinstance(base, tuple):
                return None
            fields = field_map(base)
            fd = fields.get(node.attr)
            if fd is None:
                if node.attr not in MSG_METHODS:
                    note(
                        self.fname, node.lineno, f"字段不存在: {base.name}.{node.attr}"
                    )
                return None
            if fd.is_repeated:
                # map 字段与 repeated 都归为容器
                return ("repeated", fd)
            if fd.message_type:
                return fd.message_type
            return None  # 标量
        return None

    # --- visitors ------------------------------------------------------
    def visit_Assign(self, node):
        self.visit(node.value)
        d = self.desc_of_expr(node.value)
        for t in node.targets:
            if isinstance(t, ast.Name):
                if d is not None:
                    self.vars[t.id] = d
                else:
                    self.vars.pop(t.id, None)
            else:
                self.visit(t)

    def visit_For(self, node):
        self.visit(node.iter)
        d = self.desc_of_expr(node.iter)
        if isinstance(node.target, ast.Name):
            elem = None
            if isinstance(d, tuple) and d[0] == "repeated" and d[1].message_type:
                elem = d[1].message_type
            if elem is not None:
                self.vars[node.target.id] = elem
            else:
                self.vars.pop(node.target.id, None)
        for st in node.body + node.orelse:
            self.visit(st)

    def visit_Attribute(self, node):
        # 触发字段解析(含报告)
        self.desc_of_expr(node)
        # 继续深入 value 已在 desc_of_expr 中隐式处理, 但要访问 call args 等
        self.generic_visit(node)

    def visit_Call(self, node):
        self.desc_of_expr(node)
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            self.visit(kw.value)
        # func 里的属性链也检查
        if isinstance(node.func, ast.Attribute):
            self.visit_Attribute(node.func)


def check_file(path):
    # 1. 语法
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as e:
        note(path, 0, f"编译失败: {e}")
        return

    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    # 收集 net_pb2 导入名
    pb_names = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and "net_pb2" in n.module:
            for al in n.names:
                obj = getattr(net_pb2, al.name, None)
                if obj is None:
                    note(path, n.lineno, f"net_pb2 中不存在: {al.name}")
                    continue
                if hasattr(obj, "DESCRIPTOR") and hasattr(obj.DESCRIPTOR, "fields"):
                    pb_names[al.asname or al.name] = obj

    # 2. 装饰器与 Rsp 一致性
    deco = re.findall(r"@packet_handler\(MsgId\.(\w+)\)", src)
    sends = re.findall(r"session\.send\(\s*MsgId\.(\w+)", src)
    for d in deco:
        if d not in MSG_IDS:
            note(path, 0, f"装饰器消息不存在: {d}")
    if deco:
        req = deco[0]
        rsp_expect = req[:-3] + "Rsp" if req.endswith("Req") else None
        rsp_sends = [s for s in sends if s.endswith("Rsp")]
        if rsp_expect and rsp_expect in MSG_IDS:
            if rsp_sends and rsp_expect not in rsp_sends:
                # 有的 handler 会代发别的 Rsp, 只在完全没发本 Rsp 时提示
                note(path, 0, f"疑似未回 {rsp_expect} (实际发送: {sorted(set(sends))})")
    for s in sends:
        if s not in MSG_IDS:
            note(path, 0, f"发送的消息 id 不存在: {s}")

    # 3. AST 字段校验 (按函数为作用域粗粒度跑)
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        c = Checker(path, pb_names)
        for st in fn.body:
            c.visit(st)


def main():
    files = sys.argv[1:] or sorted(glob.glob("handlers/*.py"))
    files = [f for f in files if not f.endswith("__init__.py")]

    # import + 注册重复
    seen = {}
    for f in files:
        mod = "handlers." + os.path.basename(f)[:-3]
        try:
            m = importlib.import_module(mod)
        except Exception as e:
            note(f, 0, f"import 失败: {type(e).__name__}: {e}")
            continue
        for attr in dir(m):
            obj = getattr(m, attr)
            if (
                isinstance(obj, type)
                and hasattr(obj, "msg_id")
                and obj.__module__ == mod
            ):
                mid = obj.msg_id
                if mid in seen:
                    note(f, 0, f"msg_id {mid} 与 {seen[mid]} 重复注册")
                else:
                    seen[mid] = f

    for f in files:
        check_file(f)

    if problems:
        print(f"发现 {len(problems)} 个问题:")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print(f"OK: {len(files)} 个文件, {len(seen)} 个注册, 无问题")


if __name__ == "__main__":
    main()
