"""Static guard: every item-grant call site must keep an audit declaration."""
from __future__ import annotations

import ast
import json
import unittest
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "tests" / "item_grant_audit_registry.json"
GRANT_CALLS = {
    "grant_items",
    "grant_single_item",
    "grant_character",
    "pickup_rewards",
    "grant_rewards",
    "grant_stack_item",
}
REQUIRED_FIELDS = {"category", "idempotency", "transaction", "durability"}


def call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(current)
    return "<module>"


def source_files():
    for directory in ("handlers", "server", "utils"):
        for path in (REPO / directory).rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


def actual_calls() -> Counter:
    result = Counter()
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        relative = path.relative_to(REPO.parent).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node) in GRANT_CALLS:
                result[f"{relative}::{enclosing_function(node, parents)}"] += 1
    return result


class ItemGrantAuditRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.functions = cls.registry["functions"]

    def test_every_grant_call_site_has_explicit_idempotency_and_transaction_declaration(self):
        actual = actual_calls()
        declared = {key: value["callCount"] for key, value in self.functions.items()}
        self.assertEqual(
            actual,
            Counter(declared),
            "item-grant entry points changed; update item_grant_audit_registry.json "
            "and declare category, idempotency, transaction, and durability for each function",
        )

    def test_declarations_are_complete_and_categorized(self):
        allowed_categories = {
            "collection", "gacha", "mail", "shop", "quest", "activity", "pickup",
            "drop", "reward", "dungeon", "explore", "item", "character", "other",
        }
        for key, declaration in self.functions.items():
            with self.subTest(function=key):
                self.assertTrue(REQUIRED_FIELDS <= declaration.keys())
                self.assertIn(declaration["category"], allowed_categories)
                for field in REQUIRED_FIELDS - {"category"}:
                    self.assertIsInstance(declaration[field], str)
                    self.assertTrue(declaration[field].strip())

    def test_known_critical_paths_remain_visible_to_the_audit(self):
        required = {
            "of-ps/handlers/MonsterDead.py::_handle",
            "of-ps/handlers/DailyTaskExchange.py::handle",
            "of-ps/handlers/Collecting.py::handle",
            "of-ps/handlers/ItemSweep.py::handle",
            "of-ps/handlers/DungeonSweep.py::_handle",
        }
        self.assertTrue(required <= self.functions.keys())


if __name__ == "__main__":
    unittest.main()
