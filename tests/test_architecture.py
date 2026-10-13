"""Guards the four-layer design: the layers must not import each other.
Only main.py (the controller) may know about all of them."""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYERS = {"io_manager", "ai_manager", "logic_manager", "data_manager"}

# layer -> the other layers it is allowed to import
ALLOWED = {
    "io_manager": set(),
    "ai_manager": set(),
    "logic_manager": set(),
    "data_manager": set(),
    "main": LAYERS,
}


def imported_modules(module_name):
    with open(os.path.join(ROOT, module_name + ".py"), encoding="utf-8") as file:
        tree = ast.parse(file.read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


class LayerImportTests(unittest.TestCase):
    def test_layers_do_not_import_each_other(self):
        for module_name, allowed in ALLOWED.items():
            forbidden = (imported_modules(module_name) & LAYERS) - allowed
            self.assertEqual(forbidden, set(), f"{module_name} must not import {sorted(forbidden)}")

    def test_only_the_io_manager_touches_the_terminal(self):
        for module_name in ("ai_manager", "logic_manager", "data_manager"):
            with open(os.path.join(ROOT, module_name + ".py"), encoding="utf-8") as file:
                tree = ast.parse(file.read())
            calls = [
                node.func.id for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("print", "input")
            ]
            self.assertEqual(calls, [], f"{module_name} must not call print()/input()")

    def test_importing_a_layer_prints_nothing(self):
        import contextlib
        import importlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            for name in ("logic_manager", "data_manager", "ai_manager", "io_manager"):
                importlib.reload(importlib.import_module(name))
        self.assertEqual(buffer.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
