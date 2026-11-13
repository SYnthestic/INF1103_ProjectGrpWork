"""UmlDiagrams: draws the UML class and package diagrams in docs/uml/ from
the source code, so they never fall behind it.

usage: python tools/uml_diagrams.py     (needs Graphviz: winget install graphviz)
"""

import ast
import html
import os
import shutil
import subprocess
import sys


class UmlDiagrams:
    """Reads every application file (not the tests) with ast, finds the
    classes, their attributes, methods and relationships, and writes one
    Graphviz diagram per area plus an overview and a package diagram."""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    OUTPUT = os.path.join(ROOT, "docs", "uml")
    SKIPPED_FOLDERS = {"tests", "tools", "docs", "static", "__pycache__", ".git",
                       ".venv", "venv", "env"}
    SKIPPED_FILES = {"conftest.py"}

    LOGIC_PARTS = ["managers.logic_manager.rules", "managers.logic_manager.schemes",
                   "managers.logic_manager.adjusters"]
    # (file name, title, modules drawn in full, modules left out, direction)
    AREAS = [
        ("2_controller", "Controller (main.py)", ["main", "session"], [], "TB"),
        ("3_io_manager", "I/O Manager", ["managers.io_manager", "sme_interface_stores"], [],
         "TB"),
        ("4_ai_manager", "AI Manager", ["managers.ai_manager"], [], "TB"),
        ("5_logic_manager", "Logic Manager", ["managers.logic_manager"], LOGIC_PARTS, "TB"),
        ("5b_rules_schemes_adjusters",
         "Logic Manager: eligibility rules, grant schemes and decision adjusters",
         LOGIC_PARTS, [], "LR"),
        ("6_data_manager", "Data Manager and report exporter",
         ["managers.data_manager", "report_exporter"], [], "TB"),
        ("7_models", "Shared models", ["models"], [], "TB"),
        ("8_web", "Web version (Flask)", ["app", "web"], [], "TB"),
    ]
    FAMILY_SIZE = 4  # an abstract class with this many subclasses is one box in the overview
    # Packages shown as boxes in the overview and the package diagram.
    PACKAGES = [
        ("main", "Controller"), ("session", "Controller"),
        ("managers.io_manager", "I/O Manager"), ("sme_interface_stores", "I/O Manager"),
        ("managers.ai_manager", "AI Manager"), ("managers.logic_manager", "Logic Manager"),
        ("managers.data_manager", "Data Manager"), ("report_exporter", "Data Manager"),
        ("models", "Shared models"), ("app", "Web version"), ("web", "Web version"),
    ]
    COLOURS = {
        "Controller": "#FDE9D9", "I/O Manager": "#E3F0FB", "AI Manager": "#EFE6F7",
        "Logic Manager": "#E5F3E6", "Data Manager": "#FFF4D6", "Shared models": "#EEEEEE",
        "Web version": "#E0F3F1",
    }
    MANY_METHODS = 24  # above this, methods are grouped by their first word
    FONT = "Helvetica"

    def __init__(self) -> None:
        self.classes: dict[str, dict] = {}
        self.raw_imports: dict[str, set[tuple[str, str]]] = {}

    # ----- reading the code -----
    def read(self) -> "UmlDiagrams":
        for folder, subfolders, files in os.walk(self.ROOT):
            subfolders[:] = sorted(d for d in subfolders if d not in self.SKIPPED_FOLDERS)
            for name in sorted(files):
                if name.endswith(".py") and name not in self.SKIPPED_FILES:
                    self.read_file(os.path.join(folder, name))
        for info in self.classes.values():
            info["edges"] = self.relationships(info)
        return self

    def read_file(self, path: str) -> None:
        module = os.path.relpath(path, self.ROOT)[:-3].replace(os.sep, ".")
        module = module.removesuffix(".__init__")
        with open(path, encoding="utf-8") as file:
            tree = ast.parse(file.read())
        self.raw_imports[module] = self.imported_names(tree, module, path)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self.classes[node.name] = {"node": node, "module": module,
                                           "package": self.package_of(module)}

    def package_of(self, module: str) -> str:
        for package, _ in self.PACKAGES:
            if module == package or module.startswith(package + "."):
                return package
        return module

    def imported_names(self, tree: ast.Module, module: str, path: str) -> set[tuple[str, str]]:
        """(module, name) pairs this file imports, relative imports resolved."""
        here = module if path.endswith("__init__.py") else module.rpartition(".")[0]
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update((alias.name, "") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = here.split(".")[: len(here.split(".")) - (node.level - 1)]
                    source = ".".join(base + ([node.module] if node.module else []))
                else:
                    source = node.module or ""
                found.update((source, alias.name) for alias in node.names)
        return found

    def imported_packages(self, module: str) -> set[str]:
        """Packages a module uses. `from managers import LogicManager` counts
        as the Logic Manager's package, found through the class name."""
        packages = {package for package, _ in self.PACKAGES}
        found = set()
        for source, name in self.raw_imports[module]:
            if name in self.classes:
                found.add(self.classes[name]["package"])
            else:
                found.add(self.package_of(f"{source}.{name}" if name else source))
        return found & packages

    # ----- one class -----
    def is_abstract(self, node: ast.ClassDef) -> bool:
        bases = {ast.unparse(b) for b in node.bases}
        return "ABC" in bases or any(self.decorators(m) & {"abstractmethod"}
                                     for m in self.methods(node))

    def methods(self, node: ast.ClassDef) -> list:
        return [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]

    def decorators(self, method) -> set[str]:
        return {ast.unparse(d).split("(")[0].split(".")[-1] for d in method.decorator_list}

    def short_type(self, annotation) -> str:
        if annotation is None:
            return ""
        text = ast.unparse(annotation).replace("'", "").replace('"', "")
        for prefix in ("typing.", "collections.abc."):
            text = text.replace(prefix, "")
        return text if len(text) <= 32 else text[:30] + "…"

    def visibility(self, name: str) -> str:
        if name.startswith("__") and not name.endswith("__"):
            return "-"
        return "#" if name.startswith("_") else "+"

    def attributes(self, info: dict) -> list[tuple[str, str, bool]]:
        """(text, kind, static) for class constants, instance attributes and
        properties (shown as derived attributes, /name)."""
        node, out, seen = info["node"], [], set()
        for item in node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                target = item.targets[0] if isinstance(item, ast.Assign) else item.target
                if isinstance(target, ast.Name) and target.id not in seen:
                    seen.add(target.id)
                    kind = self.short_type(item.annotation) if isinstance(item, ast.AnnAssign) \
                        else self.value_type(item.value)
                    out.append((f"{self.visibility(target.id)} {target.id}", kind, True))
        for method in self.methods(node):
            if "property" in self.decorators(method):
                name = method.name
                out.append((f"{self.visibility(name)} /{name}", self.short_type(method.returns),
                            False))
                seen.add(name)
        params = self.init_params(node)
        for method in self.methods(node):
            for item in ast.walk(method):
                if isinstance(item, (ast.Assign, ast.AnnAssign)):
                    target = item.targets[0] if isinstance(item, ast.Assign) else item.target
                    if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                            and target.value.id == "self" and target.attr not in seen):
                        seen.add(target.attr)
                        kind = self.attribute_type(item, params)
                        out.append((f"{self.visibility(target.attr)} {target.attr}", kind, False))
        return out

    def init_params(self, node: ast.ClassDef) -> dict:
        for method in self.methods(node):
            if method.name == "__init__":
                args = method.args.args + method.args.kwonlyargs
                return {a.arg: a.annotation for a in args}
        return {}

    def value_type(self, value) -> str:
        if isinstance(value, ast.Constant):
            return type(value.value).__name__ if value.value is not None else ""
        names = {ast.List: "list", ast.Tuple: "tuple", ast.Dict: "dict", ast.Set: "set",
                 ast.ListComp: "list", ast.DictComp: "dict", ast.SetComp: "set"}
        if type(value) in names:
            return names[type(value)]
        if isinstance(value, ast.Call):
            made = self.made_class(value)
            return made or ""
        if isinstance(value, ast.Name) and value.id in self.classes:
            return f"type[{value.id}]"
        return ""

    def declared(self, value, params: dict):
        """For `self.x = param` or `self.x = param or Default()`: the
        parameter's annotation, else None."""
        if isinstance(value, ast.BoolOp):
            value = value.values[0]
        if isinstance(value, ast.Name) and params.get(value.id) is not None:
            return params[value.id]
        return None

    def attribute_type(self, item, params: dict) -> str:
        if isinstance(item, ast.AnnAssign):
            return self.short_type(item.annotation)
        value = item.value
        declared = self.declared(value, params)
        if declared is not None and self.short_type(declared) not in ("Any", "Any | None"):
            return self.short_type(declared).replace(" | None", "")
        for part in ast.walk(value):
            if isinstance(part, ast.Call) and self.made_class(part):
                return self.made_class(part)
        if isinstance(value, ast.BoolOp):
            value = value.values[0]
        if isinstance(value, ast.Name) and value.id in params:
            return self.short_type(params[value.id]).replace(" | None", "")
        return self.value_type(value)

    def made_class(self, call: ast.Call) -> str | None:
        """Known class created by this call: Known(...) or Known.factory(...)."""
        func = call.func
        if isinstance(func, ast.Name) and func.id in self.classes:
            return func.id
        if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                and func.value.id in self.classes and func.attr[:1].islower()
                and func.attr.startswith(("with_", "from_", "for_", "create", "default"))):
            return func.value.id
        return None

    def method_lines(self, info: dict) -> list[tuple[str, bool, bool]]:
        """(text, abstract, static) for each method, grouped when there are many."""
        node, rows = info["node"], []
        for method in self.methods(node):
            decorators = self.decorators(method)
            if method.name.startswith("__") and method.name.endswith("__"):
                continue
            if decorators & {"property", "setter"} or method.name in {
                    a for a in decorators if a.endswith("setter")}:
                continue
            args = [a.arg for a in method.args.args + method.args.kwonlyargs
                    if a.arg not in ("self", "cls")]
            signature = ", ".join(args)
            if len(signature) > 34:
                signature = signature[:32] + "…"
            returns = self.short_type(method.returns)
            text = f"{self.visibility(method.name)} {method.name}({signature})"
            text += f" : {returns}" if returns and returns != "None" else ""
            rows.append((method.name, text, "abstractmethod" in decorators,
                         bool(decorators & {"staticmethod", "classmethod"})))
        if len(rows) <= self.MANY_METHODS:
            return [(text, abstract, static) for _, text, abstract, static in rows]
        groups: dict[str, list] = {}
        for name, text, abstract, static in rows:
            words = name.lstrip("_").split("_")
            key = (self.visibility(name), words[0] if len(words) > 1 else name.lstrip("_"))
            groups.setdefault(key, []).append((text, abstract, static))
        out = []
        for (sign, word), items in groups.items():
            if len(items) >= 3:
                prefix = "_" * (sign == "#") + word
                out.append((f"{sign} {prefix}_…()   [{len(items)} methods]", False, False))
            else:
                out.extend(items)
        return out

    # ----- relationships -----
    def relationships(self, info: dict) -> list[tuple[str, str, str]]:
        """(kind, other class, label). Kinds: inherits, composes, aggregates,
        uses, creates. The strongest relationship to each class is kept."""
        node, edges = info["node"], {}
        strength = {"inherits": 5, "composes": 4, "aggregates": 3, "uses": 2, "creates": 1}

        def add(kind: str, other: str, label: str = "") -> None:
            if other == node.name or other not in self.classes:
                return
            if other not in edges or strength[kind] > strength[edges[other][0]]:
                edges[other] = (kind, label)
            elif kind == edges[other][0] and label and not edges[other][1]:
                edges[other] = (kind, label)

        for base in node.bases:
            add("inherits", ast.unparse(base))
        params = self.init_params(node)
        for method in self.methods(node):
            raised = {id(n.exc) for n in ast.walk(method) if isinstance(n, ast.Raise) and n.exc}
            for item in ast.walk(method):
                if isinstance(item, ast.Assign):
                    target = item.targets[0]
                    if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                            and target.value.id == "self"):
                        self.attribute_edge(item.value, params, add)
                if isinstance(item, ast.Call) and method.name != "__init__":
                    made = self.made_class(item)
                    if made:
                        add("creates", made, "«raises»" if id(item) in raised else "«creates»")
                    elif (isinstance(item.func, ast.Attribute)
                          and isinstance(item.func.value, ast.Name)
                          and item.func.value.id in self.classes):
                        add("uses", item.func.value.id)
        return [(kind, other, label) for other, (kind, label) in edges.items()]

    def attribute_edge(self, value, params: dict, add) -> None:
        declared = self.declared(value, params)
        declared_classes = self.classes_in(declared)
        for part in ast.walk(value):
            if isinstance(part, ast.Call) and self.made_class(part):
                made = self.made_class(part)
                if declared_classes and made not in declared_classes:
                    # Depends on the abstraction; the concrete class is only the default.
                    for other in declared_classes:
                        add("composes", other)
                    add("creates", made, "«default»")
                else:
                    add("composes", made)
                return
        if isinstance(value, ast.BoolOp):
            value = value.values[0]
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                and value.func.id in ("tuple", "list") and value.args:
            value = value.args[0]
        if isinstance(value, ast.Name) and value.id in self.classes:
            add("uses", value.id)
        elif isinstance(value, ast.Name) and params.get(value.id) is not None:
            text = ast.unparse(params[value.id])
            many = text.startswith(("Sequence", "list", "tuple", "Iterable"))
            for other in self.classes_in(params[value.id]):
                add("aggregates", other, "1..*" if many else "")

    def classes_in(self, annotation) -> list[str]:
        if annotation is None:
            return []
        words = ast.unparse(annotation)
        for mark in "|[],'\"":
            words = words.replace(mark, " ")
        return [w for w in words.split() if w in self.classes]

    # ----- drawing -----
    def escape(self, text: str) -> str:
        return html.escape(text, quote=True)

    def class_label(self, info: dict, full: bool) -> str:
        node = info["node"]
        abstract = self.is_abstract(node)
        external = [ast.unparse(b) for b in node.bases
                    if ast.unparse(b) not in self.classes and ast.unparse(b) != "ABC"]
        title = f"<I>{self.escape(node.name)}</I>" if abstract else self.escape(node.name)
        stereotype = "«abstract»<BR/>" if abstract else ""
        if external:
            stereotype = f"«{self.escape(', '.join(external))}»<BR/>"
        stereotype = f'<FONT POINT-SIZE="9">{stereotype}</FONT>' if stereotype else ""
        rows = [f"<TR><TD>{stereotype}<B>{title}</B></TD></TR>"]
        if full:
            attributes = self.attributes(info)
            lines = []
            for text, kind, static in attributes:
                line = self.escape(text + (f" : {kind}" if kind else ""))
                lines.append(f"<U>{line}</U>" if static else line)
            rows.append(self.section(lines))
            lines = []
            for text, abstract_method, static in self.method_lines(info):
                line = self.escape(text)
                line = f"<I>{line}</I>" if abstract_method else line
                lines.append(f"<U>{line}</U>" if static else line)
            rows.append(self.section(lines))
        return ('<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">'
                + "".join(rows) + "</TABLE>>")

    def section(self, lines: list[str]) -> str:
        body = '<BR ALIGN="LEFT"/>'.join(lines) + '<BR ALIGN="LEFT"/>' if lines else " "
        return f'<TR><TD ALIGN="LEFT" BALIGN="LEFT"><FONT POINT-SIZE="9">{body}</FONT></TD></TR>'

    def edge(self, owner: str, kind: str, other: str, label: str) -> str:
        """Parents and owners are drawn above, so every edge runs top-down."""
        styles = {
            "inherits": f'"{other}" -> "{owner}" [dir=back, arrowtail=empty]',
            "composes": f'"{owner}" -> "{other}" [dir=both, arrowtail=diamond, arrowhead=vee]',
            "aggregates": f'"{owner}" -> "{other}" [dir=both, arrowtail=odiamond, arrowhead=vee]',
            "uses": f'"{owner}" -> "{other}" [style=dashed, arrowhead=vee]',
            "creates": f'"{owner}" -> "{other}" [style=dashed, arrowhead=vee]',
        }
        line = styles[kind]
        if label:
            line = line[:-1] + f', label="{label}", fontsize=9]'
        return line

    def header(self, title: str, direction: str = "TB") -> list[str]:
        return [
            "digraph uml {",
            f'  graph [rankdir={direction}, fontname="{self.FONT}", fontsize=16, labelloc=t, '
            f'label="{title}", nodesep=0.35, ranksep=0.55, newrank=true, pad=0.3];',
            f'  node [shape=plain, fontname="{self.FONT}", fontsize=10];',
            f'  edge [fontname="{self.FONT}", fontsize=9, color="#444444"];',
        ]

    def area(self, packages: list[str]) -> str:
        for package, area in self.PACKAGES:
            if package in packages:
                return area
        return ""

    def in_modules(self, module: str, prefixes: list[str]) -> bool:
        return any(module == p or module.startswith(p + ".") for p in prefixes)

    def family_of(self, name: str) -> str | None:
        """The abstract base of a large family of subclasses (the rules,
        the schemes), or None."""
        for base in self.classes[name]["node"].bases:
            base = ast.unparse(base)
            if base in self.classes and self.is_abstract(self.classes[base]["node"]):
                members = [c for c, i in self.classes.items()
                           if base in {ast.unparse(b) for b in i["node"].bases}]
                if len(members) >= self.FAMILY_SIZE:
                    return base
        return None

    def class_diagram(self, title: str, include: list[str], exclude: list[str],
                      direction: str) -> str:
        inside = [c for c, info in self.classes.items()
                  if self.in_modules(info["module"], include)
                  and not self.in_modules(info["module"], exclude)]
        lines = self.header(title, direction)
        clusters: dict[str, list[str]] = {}
        for name in inside:
            module = self.classes[name]["module"]
            parts = module.split(".")
            sub = ".".join(parts[:-1]) if len(parts) > 1 else parts[0]
            clusters.setdefault(sub, []).append(name)
        colour = self.COLOURS.get(self.area([self.classes[inside[0]]["package"]]), "#FFFFFF")
        for number, (sub, names) in enumerate(sorted(clusters.items())):
            lines.append(f'  subgraph cluster_{number} {{ label="{sub}"; style="rounded,filled";'
                         f' fillcolor="{colour}"; color="#999999"; fontsize=11;')
            for name in names:
                label = self.class_label(self.classes[name], full=True)
                lines.append(f'    "{name}" [label={label}, style=filled, fillcolor=white];')
            lines.append("  }")
        outside, drawn = set(), {}
        for name in inside:
            for kind, other, label in self.classes[name]["edges"]:
                if other not in inside and kind in ("creates", "uses") and self.family_of(other):
                    other = self.family_of(other)  # "creates every rule" -> one line
                    label = "«creates subclasses»" if kind == "creates" else label
                if (name, other) in drawn or other == name:
                    continue
                drawn[(name, other)] = kind
                if other not in inside:
                    outside.add(other)
                lines.append("  " + self.edge(name, kind, other, label))
        for name in sorted(outside):
            label = self.class_label(self.classes[name], full=False)
            lines.append(f'  "{name}" [label={label}, color="#888888", fontcolor="#555555"];')
        lines.append("}")
        return "\n".join(lines)

    def overview(self) -> str:
        """Class names only. Each large family of subclasses is one box, and
        only inheritance, composition and aggregation are drawn."""
        lines = self.header("Overview: every class and how they relate")
        node_of = {}
        for name in self.classes:
            family = self.family_of(name)
            node_of[name] = f"{family}*" if family else name
        by_area: dict[str, list[str]] = {}
        for name, info in self.classes.items():
            if node_of[name] == name:
                by_area.setdefault(self.area([info["package"]]), []).append(name)
            elif node_of[name] not in by_area.setdefault(self.area([info["package"]]), []):
                by_area[self.area([info["package"]])].append(node_of[name])
        for number, (area, names) in enumerate(by_area.items()):
            lines.append(f'  subgraph cluster_{number} {{ label="{area}"; style="rounded,filled";'
                         f' fillcolor="{self.COLOURS.get(area, "#FFFFFF")}"; color="#999999";')
            for name in names:
                if name.endswith("*"):
                    members = sorted(c for c, n in node_of.items() if n == name)
                    label = (f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" '
                             f'CELLPADDING="4"><TR><TD><B>{len(members)} {name[:-1]} '
                             f'subclasses</B><BR/><FONT POINT-SIZE="8">'
                             + "<BR/>".join(members) + "</FONT></TD></TR></TABLE>>")
                else:
                    label = self.class_label(self.classes[name], full=False)
                lines.append(f'    "{name}" [label={label}, style=filled, fillcolor=white];')
            lines.append("  }")
        drawn = set()
        for name, info in self.classes.items():
            for kind, other, label in info["edges"]:
                if kind in ("inherits", "composes", "aggregates"):
                    edge = (node_of[name], kind, node_of[other])
                    if edge in drawn or node_of[name] == node_of[other]:
                        continue
                    drawn.add(edge)
                    lines.append("  " + self.edge(node_of[name], kind, node_of[other], label))
        lines.append("}")
        return "\n".join(lines)

    def package_diagram(self) -> str:
        lines = self.header("Packages and their imports")
        lines[2] = (f'  node [shape=tab, style=filled, fontname="{self.FONT}", fontsize=11, '
                    'margin="0.2,0.1"];')
        for package, area in self.PACKAGES:
            lines.append(f'  "{package}" [fillcolor="{self.COLOURS[area]}"];')
        lines.append('  { rank=same; "managers.io_manager"; "managers.ai_manager"; '
                     '"managers.logic_manager"; "managers.data_manager"; }')
        edges = set()
        for module in self.raw_imports:
            source = self.package_of(module)
            if source not in dict(self.PACKAGES):
                continue
            for target in self.imported_packages(module):
                if target != source:
                    edges.add((source, target))
        for source, target in sorted(edges):
            lines.append(f'  "{source}" -> "{target}" [style=dashed, arrowhead=vee];')
        lines.append("}")
        return "\n".join(lines)

    # ----- writing -----
    def write_all(self) -> list[str]:
        dot = shutil.which("dot")
        if dot is None:
            raise SystemExit("Graphviz is not installed. Install it (Windows: "
                             "winget install graphviz) and open a new terminal.")
        os.makedirs(self.OUTPUT, exist_ok=True)
        diagrams = [("0_packages", self.package_diagram()), ("1_overview", self.overview())]
        diagrams += [(name, self.class_diagram(title, include, exclude, direction))
                     for name, title, include, exclude, direction in self.AREAS]
        written = []
        for name, source in diagrams:
            path = os.path.join(self.OUTPUT, name)
            for fmt, extra in (("png", ["-Gdpi=150"]), ("svg", [])):
                subprocess.run([dot, f"-T{fmt}", *extra, "-o", f"{path}.{fmt}"],
                               input=source.encode("utf-8"), check=True)
            written.append(path + ".png")
        return written


if __name__ == "__main__":
    sys.exit(0 if UmlDiagrams().read().write_all() else 1)
