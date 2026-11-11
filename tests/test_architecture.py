"""Guards the four-manager design and the object-oriented structure.

* The four managers must not import each other. Only main.py (the controller)
  may know about all of them.
* Only the I/O Manager prints or asks for input.
* No procedural code: application modules contain classes (and constants)
  only.
* Every abstraction the design relies on really is abstract and has concrete
  implementations.

The checks read every application file, so new files are covered
automatically.
"""

import ast
import inspect
import os
import subprocess
import sys
from abc import ABC

import managers.ai as ai
import managers.data_manager as data_manager
import managers.io_manager as io_manager
import managers.logic_manager as logic_manager
import models
import report_exporter
import web.audits
import web.auth
import web.pages
import web.routes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIPPED_FOLDERS = {"tests", "__pycache__", ".git", ".venv", "venv", "env", "static"}

# Which local packages each manager may import besides itself. Anything else
# local (another manager, main, session, web, app) is forbidden.
MANAGER_ALLOWED = {
    "managers.io_manager": {"models", "sme_interface_stores"},
    "managers.ai": {"models"},
    "managers.logic_manager": {"models"},
    "managers.data_manager": {"models", "report_exporter"},
}
LOCAL_TOP_LEVEL = {
    "managers", "models", "report_exporter", "sme_interface_stores",
    "session", "main", "app", "web",
}

# Module-level functions that a framework requires, and why. Nothing else may
# be a module-level function.
REQUIRED_FUNCTIONS = {
    # Flask's CLI (`flask --app app run`) only accepts a plain function named
    # create_app as the app factory; it hands straight over to WebApplication.
    ("app", "create_app"),
}


def application_files():
    """{module name: path} for every application .py file (not the tests)."""
    found = {}
    for folder, subfolders, files in os.walk(ROOT):
        subfolders[:] = [d for d in subfolders if d not in SKIPPED_FOLDERS]
        for name in files:
            if not name.endswith(".py") or name == "conftest.py":
                continue
            path = os.path.join(folder, name)
            relative = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
            module = relative[: -len(".__init__")] if relative.endswith(".__init__") else relative
            found[module] = path
    return found


FILES = application_files()


def parse(module):
    with open(FILES[module], encoding="utf-8") as file:
        return ast.parse(file.read())


def imported_modules(module):
    """Full dotted names of the local modules `module` imports (relative
    imports resolved), e.g. {"models", "managers.logic_manager.case"}."""
    package = module if FILES[module].endswith("__init__.py") else module.rpartition(".")[0]
    found = set()
    for node in ast.walk(parse(module)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            found.add(target)
    return {name for name in found if name.split(".")[0] in LOCAL_TOP_LEVEL}


def belongs_to(name, package):
    return name == package or name.startswith(package + ".")


def test_every_application_module_is_found():
    assert "managers.logic_manager" in FILES and "managers.data_manager" in FILES
    assert "web.pages" in FILES and "app" in FILES and "main" in FILES


def test_managers_do_not_import_each_other():
    for manager, allowed in MANAGER_ALLOWED.items():
        for module in (m for m in FILES if belongs_to(m, manager)):
            for name in imported_modules(module):
                ok = belongs_to(name, manager) or any(
                    belongs_to(name, other) for other in allowed
                )
                assert ok, f"{module} must not import {name}"


def test_the_controller_uses_only_the_managers_models_and_session():
    for name in imported_modules("main"):
        assert name.split(".")[0] in {"managers", "models", "session"}, name


def test_only_the_io_manager_touches_the_terminal():
    for module in FILES:
        if belongs_to(module, "managers.io_manager"):
            continue
        calls = [
            node.func.id
            for node in ast.walk(parse(module))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("print", "input")
        ]
        assert calls == [], f"{module} must not call print()/input()"


def test_importing_a_manager_prints_nothing():
    """Imported in a fresh interpreter (reloading modules in this process would
    create second copies of every class and break isinstance checks)."""
    code = (
        "import models, report_exporter, main; "
        "import managers.logic_manager, managers.data_manager, "
        "managers.ai, managers.io_manager"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""


def test_no_procedural_code_is_left():
    """Application modules hold classes (and constants) only: no module-level
    functions, apart from the framework entry points listed above."""
    offenders = []
    for module in FILES:
        for node in parse(module).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (module, node.name) not in REQUIRED_FUNCTIONS:
                    offenders.append(f"{module}:{node.lineno} {node.name}")
    assert offenders == [], f"module-level functions found: {offenders}"


def test_the_controller_does_not_import_the_screen_art_directly():
    """main.py talks to the screens only through io_manager."""
    assert not any(belongs_to(n, "sme_interface_stores") for n in imported_modules("main"))


def concrete_subclasses(base):
    found = []
    for module in (logic_manager, ai, report_exporter, models, data_manager,
                   web.pages, web.auth, web.audits):
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
        models.FileCipher,
        ai.AIClient,
        report_exporter.ReportExporter,
        web.routes.RouteGroup,
    )
    for base in abstractions:
        assert issubclass(base, ABC), base.__name__
        assert inspect.isabstract(base), f"{base.__name__} can be instantiated"
        assert concrete_subclasses(base), f"{base.__name__} has no implementation"


def test_the_four_managers_exist_as_classes():
    assert inspect.isclass(io_manager.IOManager)
    assert inspect.isclass(ai.AIManager)
    assert inspect.isclass(logic_manager.LogicManager)
    assert inspect.isclass(data_manager.DataManager)


def test_the_web_app_is_still_found_by_flask_and_gunicorn(tmp_path):
    """create_app must stay a plain function, or `flask --app app run` cannot
    find the app (it ignores a class method under that name)."""
    import app

    assert inspect.isfunction(app.create_app)
    done = subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app", "routes"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "DATA_DIR": str(tmp_path)},
    )
    assert done.returncode == 0, done.stderr
    assert "pages.home" in done.stdout and "audits.create_audit" in done.stdout
