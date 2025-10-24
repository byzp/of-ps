# descriptor_to_single_proto.py
# Usage: python descriptor_to_single_proto.py net_descriptor_set.bytes out_file.proto
#
# This version improves on the previous by:
# - Detecting synthetic map entry messages ("*Entry") and emitting `map<key, value>` fields
#   instead of repeating the synthetic message type.
# - Converting field names to snake_case (common proto style) when writing fields.
# - Skipping synthetic map entry message definitions when emitting messages.
# - Stripping package prefixes for types that are local to the descriptor set.
# - Conservatively emitting imports declared by files.

import sys
import re
import os
from google.protobuf import descriptor_pb2

TYPE_MAP = {
    1: "double",
    2: "float",
    3: "int64",
    4: "uint64",
    5: "int32",
    6: "fixed64",
    7: "fixed32",
    8: "bool",
    9: "string",
    10: "group",
    11: "message",
    12: "bytes",
    13: "uint32",
    14: "enum",
    15: "sfixed32",
    16: "sfixed64",
    17: "sint32",
    18: "sint64",
}

LABEL_MAP = {
    1: "",  # optional in proto3 omitted
    2: "required ",  # rarely used in proto3
    3: "repeated ",
}

CAMEL_SPLIT_RE = re.compile(r"(?<!^)(?=[A-Z0-9])")
SNAKE_CLEAN_RE = re.compile(r"[^0-9a-z_]")


def to_snake(name: str) -> str:
    # convert CamelCase or camelCase or mixedCase to snake_case
    if not name:
        return name
    # replace dots with underscores (field names should not contain dots)
    name = name.replace(".", "_")
    # split at uppercase boundaries
    parts = CAMEL_SPLIT_RE.split(name)
    parts = [p.lower() for p in parts if p]
    s = "_".join(parts)
    # collapse repeated underscores and remove invalid chars
    s = re.sub(r"_+", "_", s)
    s = SNAKE_CLEAN_RE.sub("", s)
    # ensure it doesn't start with digit
    if s and s[0].isdigit():
        s = "_" + s
    return s


def write_indent(f, s, indent=0):
    f.write("    " * indent + s + "\n")


def collect_types_and_map_entries(fds):
    """
    Collects two things:
      - local_types: mapping from full_name (no leading dot) -> file package (or None)
      - map_entries: set of full names that are synthetic map entry messages
        mapping full_name -> (key_field_descriptor, value_field_descriptor)
    """
    local_types = {}
    map_entries = {}

    def add_message(package, prefix, msg):
        full = ".".join(
            [
                p
                for p in ([package] if package else [])
                + ([prefix] if prefix else [])
                + [msg.name]
                if p
            ]
        )
        local_types[full] = package
        # nested messages
        for nested in msg.nested_type:
            nfull = ".".join(
                [
                    p
                    for p in ([package] if package else [])
                    + ([prefix] if prefix else [])
                    + [msg.name, nested.name]
                    if p
                ]
            )
            # detect synthetic map entry
            if nested.options.map_entry:
                # find key/value fields inside nested
                key = None
                val = None
                for f in nested.field:
                    if f.name == "key":
                        key = f
                    elif f.name == "value":
                        val = f
                if key and val:
                    map_entries[nfull] = (key, val)
                # do not recurse into map entry
            else:
                add_message(
                    package,
                    ".".join([prefix, msg.name]) if prefix else msg.name,
                    nested,
                )
        # enums inside message
        for e in msg.enum_type:
            efull = ".".join(
                [
                    p
                    for p in ([package] if package else [])
                    + ([prefix] if prefix else [])
                    + [msg.name, e.name]
                    if p
                ]
            )
            local_types[efull] = package

    for fd in fds.file:
        pkg = fd.package
        for m in fd.message_type:
            add_message(pkg, "", m)
        for e in fd.enum_type:
            full = ".".join([pkg, e.name]) if pkg else e.name
            local_types[full] = pkg
    return local_types, map_entries


def dump_enum(f, enum, indent=0):
    write_indent(f, f"enum {enum.name} {{", indent)
    for v in enum.value:
        write_indent(f, f"{v.name} = {v.number};", indent + 1)
    write_indent(f, "}", indent)
    write_indent(f, "", 0)


def type_name_to_local(tn: str, local_types: dict):
    """Strip package prefix if tn is a local type. tn must not have leading dot."""
    if not tn:
        return tn
    if tn in local_types:
        pkg = local_types[tn]
        if pkg and tn.startswith(pkg + "."):
            return tn[len(pkg) + 1 :]
        else:
            return tn.split(".", 1)[-1]
    return tn


def dump_message(f, msg, local_types, map_entries, pkg, indent=0):
    # skip synthetic map entry messages if they were recorded
    # (caller is responsible for not calling dump_message on map entries)
    write_indent(f, f"message {msg.name} {{", indent)
    # enums
    for e in msg.enum_type:
        dump_enum(f, e, indent + 1)
    # nested messages: skip map_entry synthetic ones
    for n in msg.nested_type:
        # compute full nested name
        full_nested = ".".join(
            [p for p in ([pkg] if pkg else []) + [msg.name, n.name] if p]
        )
        if n.options.map_entry and full_nested in map_entries:
            # skip emitting synthetic map entry type
            continue
        dump_message(f, n, local_types, map_entries, pkg, indent + 1)
    # fields
    for field in msg.field:
        # convert field name to snake_case
        fname = to_snake(field.name)
        label = LABEL_MAP.get(field.label, "")
        if (
            field.type == descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            or field.type == descriptor_pb2.FieldDescriptorProto.TYPE_ENUM
        ):
            tn = field.type_name.lstrip(".")
            # detect map entry
            if tn in map_entries:
                key_fd, val_fd = map_entries[tn]
                # determine key type
                if key_fd.type == descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE:
                    key_type = type_name_to_local(
                        key_fd.type_name.lstrip("."), local_types
                    )
                else:
                    key_type = TYPE_MAP.get(key_fd.type, "/*unknown*/")
                # determine value type
                if (
                    val_fd.type == descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                    or val_fd.type == descriptor_pb2.FieldDescriptorProto.TYPE_ENUM
                ):
                    value_type = type_name_to_local(
                        val_fd.type_name.lstrip("."), local_types
                    )
                else:
                    value_type = TYPE_MAP.get(val_fd.type, "/*unknown*/")
                write_indent(
                    f,
                    f"map<{key_type}, {value_type}> {fname} = {field.number};",
                    indent + 1,
                )
            else:
                # normal message/enum field
                if tn in local_types:
                    t = type_name_to_local(tn, local_types)
                else:
                    t = tn
                write_indent(f, f"{label}{t} {fname} = {field.number};", indent + 1)
        else:
            t = TYPE_MAP.get(field.type, "/*unknown*/")
            write_indent(f, f"{label}{t} {fname} = {field.number};", indent + 1)
    write_indent(f, "}", indent)
    write_indent(f, "", 0)


def main():
    if len(sys.argv) < 3:
        print(
            "Usage: python descriptor_to_single_proto.py net_descriptor_set.bytes out_file.proto"
        )
        return
    inpath = sys.argv[1]
    outpath = sys.argv[2]

    with open(inpath, "rb") as rf:
        data = rf.read()
    fds = descriptor_pb2.FileDescriptorSet()
    fds.ParseFromString(data)

    local_types, map_entries = collect_types_and_map_entries(fds)

    # choose syntax and package (if all files share same non-empty package, emit it)
    syntaxes = set(fd.syntax for fd in fds.file if fd.syntax)
    syntax = next(iter(syntaxes)) if syntaxes else "proto2"

    packages = set(fd.package for fd in fds.file if fd.package)
    package = packages.pop() if len(packages) == 1 else None

    # collect unique dependencies
    all_deps = []
    for fd in fds.file:
        for d in fd.dependency:
            if d not in all_deps:
                all_deps.append(d)

    with open(outpath, "w", encoding="utf-8") as f:
        write_indent(f, f'syntax = "{syntax}";')
        if package:
            write_indent(f, f"package {package};")
            write_indent(f, "")

        for dep in all_deps:
            write_indent(f, f'import "{dep}";')
        if all_deps:
            write_indent(f, "")

        for fd in fds.file:
            # file-level enums
            for e in fd.enum_type:
                dump_enum(f, e, 0)
            # file-level messages
            for m in fd.message_type:
                # skip top-level map entry types (unlikely but handle defensively)
                full_m = ".".join(
                    [p for p in ([fd.package] if fd.package else []) + [m.name] if p]
                )
                if full_m in map_entries:
                    continue
                dump_message(f, m, local_types, map_entries, fd.package, 0)
            # services
            for s in fd.service:
                write_indent(f, f"service {s.name} {{")
                for method in s.method:
                    in_t = method.input_type.lstrip(".")
                    out_t = method.output_type.lstrip(".")
                    if in_t in local_types:
                        in_t = type_name_to_local(in_t, local_types)
                    if out_t in local_types:
                        out_t = type_name_to_local(out_t, local_types)
                    write_indent(f, f"rpc {method.name}({in_t}) returns ({out_t});", 1)
                write_indent(f, "}", 0)
    print(f"Wrote: {outpath}")


if __name__ == "__main__":
    main()
