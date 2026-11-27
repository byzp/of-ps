"""Inventory and placeholder regression checks for every packet handler.

This test intentionally imports handlers without starting a server or initializing
mutable game state.  The small allowlist documents the one intentional no-op;
new empty implementations must be implemented or explicitly reviewed here.
"""

import ast
import importlib
import inspect
import re
import sys
from pathlib import Path

import pytest

from network.packet_handler import PacketHandler


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HANDLER_DIR = REPO_ROOT / "handlers"
HANDLER_FILES = tuple(
    path for path in sorted(HANDLER_DIR.glob("*.py")) if path.name != "__init__.py"
)

# (module stem, qualified function name): reviewed intentional no-ops only.
UNSUPPORTED_NOOPS = frozenset({("ActivitySandbagHit", "sb_save")})
PLACEHOLDER_MARKER = re.compile(r"\b(?:TODO|FIXME|XXX|NotImplemented)\b", re.IGNORECASE)


def _module_name(path):
    return f"handlers.{path.stem}"


def _is_docstring(statement):
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


@pytest.mark.parametrize("path", HANDLER_FILES, ids=lambda path: path.stem)
def test_handler_file_imports_and_exposes_concrete_handle(path):
    module = importlib.import_module(_module_name(path))
    handler_class = getattr(module, "Handler", None)
    assert inspect.isclass(handler_class), f"{path.name} must define class Handler"
    assert issubclass(handler_class, PacketHandler), (
        f"{path.name}: Handler must subclass PacketHandler"
    )
    assert not inspect.isabstract(handler_class), (
        f"{path.name}: Handler must implement all abstract methods"
    )
    handle = getattr(handler_class, "handle", None)
    assert callable(handle), f"{path.name}: Handler.handle must be callable"
    parameters = tuple(inspect.signature(handle).parameters.values())
    assert len(parameters) >= 4, (
        f"{path.name}: handle must accept self, session, data, and packet_id"
    )
    assert tuple(parameter.name for parameter in parameters[1:4]) == (
        "session", "data", "packet_id"
    ), (
        f"{path.name}: handle interface must be handle(self, session, data, packet_id)"
    )


def test_inventory_contains_all_303_handlers():
    assert len(HANDLER_FILES) == 303, (
        "handler inventory changed; review additions/removals and update this baseline"
    )
    assert len({path.stem for path in HANDLER_FILES}) == len(HANDLER_FILES)


@pytest.mark.parametrize("path", HANDLER_FILES, ids=lambda path: path.stem)
def test_handler_has_no_unreviewed_placeholders(path):
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(path))
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = [statement for statement in node.body if not _is_docstring(statement)]
            if body and all(isinstance(statement, ast.Pass) for statement in body):
                parent = parents.get(node)
                prefix = []
                while parent is not None:
                    if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        prefix.append(parent.name)
                    parent = parents.get(parent)
                qualified_name = ".".join([*reversed(prefix), node.name])
                assert (path.stem, qualified_name) in UNSUPPORTED_NOOPS, (
                    f"{path.name}:{node.lineno}: empty implementation {qualified_name}; "
                    "implement it or add a reviewed entry to UNSUPPORTED_NOOPS"
                )

    for line_number, line in enumerate(source.splitlines(), 1):
        assert not PLACEHOLDER_MARKER.search(line), (
            f"{path.name}:{line_number}: unresolved placeholder marker"
        )
