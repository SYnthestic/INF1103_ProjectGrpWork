"""Guards the four-manager design and the object-oriented structure.

* The four managers must not import each other. Only main.py (the controller)
  may know about all of them.
* Only the I/O Manager prints or asks for input.
* No procedural code is left: application modules contain classes only.
* Every abstraction the design relies on really is abstract and has concrete
  implementations.
"""

import ast
import inspect
import os
import subprocess
import sys
from abc import ABC

import managers.ai_manager as ai_manager
import managers.data_manager as data_manager
import managers.io_manager as io_manager
import managers.logic_manager as logic_manager
import models
import report_exporter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANAGERS = {
    "managers.io_manager",
    "managers.ai_manager",
    "managers.logic_manager",
    "managers.data_manager",
}
MODULE_PATHS = {
    "main": "main.py",
    "models": "models.py",
    "session": "session.py",
    "report_exporter": "report_exporter.py",
    "managers.io_manager": "managers/io_manager.py",
    "managers.ai_manager": "managers/ai_manager.py",
    "managers.logic_manager": "managers/logic_manager.py",
    "managers.data_manager": "managers/data_manager.py",
    "sme_interface_stores.sme_interface_gui":
    "sme_interface_stores/sme_interface_gui.py",
}
APPLICATION_MODULES = (
    "main",
    "models",
    "managers.io_manager",
    "managers.ai_manager",
    "managers.logic_manager",
    "managers.data_manager",
    "report_exporter",
    "sme_interface_stores.sme_interface_gui",
)

# Shared support modules every manager may use. They hold no manager logic.
SUPPORT_MODULES = {"models", "report_exporter", "sme_interface_stores"}
ALLOWED = {
    "managers.io_manager": SUPPORT_MODULES,
    "managers.ai_manager": SUPPORT_MODULES,
    "managers.logic_manager": SUPPORT_MODULES,
    "managers.data_manager": SUPPORT_MODULES,
    "main": MANAGERS | {"models", "session"},
}

def parse(module_name):
    path = os.path.join(ROOT, MODULE_PATHS[module_name])
    with open(path, encoding="utf-8") as file:
        return ast.parse(file.read())


def imported_modules(module_name):
    found = set()
    for node in ast.walk(parse(module_name)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def local_modules():
    names = {name[:-3] for name in os.listdir(ROOT) if name.endswith(".py")}
    names.add("sme_interface_stores")
    return names


def test_managers_do_not_import_each_other():
    local = local_modules()
    for module_name, allowed in ALLOWED.items():
        local_imports = (imported_modules(module_name) & local) - {module_name}
        forbidden = local_imports - allowed
        assert forbidden == set(), f"{module_name} must not import {sorted(forbidden)}"


def test_only_the_io_manager_touches_the_terminal():
    for module_name in APPLICATION_MODULES:
        if module_name.rsplit(".", 1)[-1] == "io_manager":
            continue
        calls = [
            node.func.id
            for node in ast.walk(parse(module_name))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("print", "input")
        ]
        assert calls == [], f"{module_name} must not call print()/input()"


def test_importing_a_manager_prints_nothing():
    """Imported in a fresh interpreter (reloading modules in this process would
    create second copies of every class and break isinstance checks)."""
    code = (
    "import models, report_exporter, main; "
    "import managers.logic_manager, managers.data_manager, "
    "managers.ai_manager, managers.io_manager"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""


def test_no_procedural_code_is_left():
    """Application modules hold classes (and constants) only: no module-level
    functions."""
    offenders = []
    for module_name in APPLICATION_MODULES:
        for node in parse(module_name).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                offenders.append(f"{module_name}:{node.lineno} {node.name}")
    assert offenders == [], f"module-level functions found: {offenders}"


def test_the_controller_does_not_import_the_screen_art_directly():
    """main.py talks to the screens only through io_manager."""
    assert "sme_interface_stores" not in imported_modules("main")


def concrete_subclasses(base):
    found = []
    for module in (logic_manager, ai_manager, report_exporter, models, data_manager):
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(candidate, base)
                and candidate is not base
                and not inspect.isabstract(candidate)
            ):
                found.append(candidate)
    return found


def test_the_design_abstractions_are_real_abstract_classes():
    abstractions = (
        logic_manager.EligibilityRule,
        logic_manager.GrantScheme,
        logic_manager.DecisionAdjuster,
        models.Proposal,
        ai_manager.AIClient,
        report_exporter.ReportExporter,
    )
    for base in abstractions:
        assert issubclass(base, ABC), base.__name__
        assert inspect.isabstract(base), f"{base.__name__} can be instantiated"
        assert concrete_subclasses(base), f"{base.__name__} has no implementation"


def test_the_four_managers_exist_as_classes():
    assert inspect.isclass(io_manager.IOManager)
    assert inspect.isclass(ai_manager.AIManager)
    assert inspect.isclass(logic_manager.LogicManager)
    assert inspect.isclass(data_manager.DataManager)
