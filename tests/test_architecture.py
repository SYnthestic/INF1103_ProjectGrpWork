"""Guards the four-layer design: the layers must not import each other.
Only main.py (the controller) may know about all of them."""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYERS = {"io_manager", "ai_manager", "logic_manager", "data_manager"}
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
            found.update((alias.name.split(".")[0] for alias in node.names))
        elif isinstance(node, ast.ImportFrom) and node.module and (node.level == 0):
            found.add(node.module.split(".")[0])
    return found


def test_layers_do_not_import_each_other():
    for module_name, allowed in ALLOWED.items():
        forbidden = (imported_modules(module_name) & LAYERS) - allowed
        assert forbidden == set(), f"{module_name} must not import {sorted(forbidden)}"


def test_only_the_io_manager_touches_the_terminal():
    for module_name in ("ai_manager", "logic_manager", "data_manager", "main"):
        with open(os.path.join(ROOT, module_name + ".py"), encoding="utf-8") as file:
            tree = ast.parse(file.read())
        calls = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and (node.func.id in ("print", "input"))
        ]
        assert calls == [], f"{module_name} must not call print()/input()"


def test_importing_a_layer_prints_nothing():
    import contextlib
    import importlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        for name in ("logic_manager", "data_manager", "ai_manager", "io_manager"):
            importlib.reload(importlib.import_module(name))
    assert buffer.getvalue() == ""


def test_no_class_definitions_anywhere():
    """The project is 100% procedural: no `class` in any .py file (tests too)."""
    offenders = []
    for folder, subfolders, files in os.walk(ROOT):
        subfolders[:] = [
            name for name in subfolders if not name.startswith((".", "__"))
        ]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as file:
                    tree = ast.parse(file.read())
                offenders += [
                    f"{os.path.relpath(path, ROOT)}:{node.lineno}"
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ClassDef)
                ]
    assert offenders == [], f"classes found: {offenders}"


def test_the_controller_does_not_import_the_screen_art_directly():
    """main.py talks to the screens only through io_manager."""
    assert "sme_interface_stores" not in imported_modules("main")
