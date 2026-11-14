"""Architecture rules: dependencies only point downward.

    api        routes/, graphql/, middleware/, workers/, main.py   (HTTP and jobs)
      v
    services   services/<domain>/, managers/, auth/, security/   (business rules)
      v
    data       db/
      v
    utils      utils/, prompts/, assets/                          (no app knowledge)

A failure here means a module reached *up* a layer. Move the shared piece
down (or into the right domain package) instead of adding an exception.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

API = ("app.routes", "app.graphql", "app.middleware", "app.workers", "app.main")
SERVICES = ("app.services", "app.managers", "app.auth", "app.security")

RULES = {
    # package prefix of the importing module -> prefixes it must never import
    "app.services": API,
    "app.managers": API,
    "app.auth": API,
    "app.security": API,
    "app.db": API + ("app.services", "app.managers", "app.auth"),
    "app.utils": API + SERVICES + ("app.db",),
    "app.prompts": API + SERVICES + ("app.db",),
    "app.assets": API + SERVICES + ("app.db",),
}


def _module_name(path: Path) -> str:
    parts = path.relative_to(APP.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return {name for name in found if name.startswith("app.") or name == "app"}


def _violations() -> list[str]:
    problems = []
    for path in sorted(APP.rglob("*.py")):
        module = _module_name(path)
        forbidden = next((rule for prefix, rule in RULES.items() if module == prefix or module.startswith(prefix + ".")), ())
        for imported in sorted(_imports(path)):
            if any(imported == f or imported.startswith(f + ".") for f in forbidden):
                problems.append(f"{module} imports {imported}")
    return problems


def test_lower_layers_never_import_higher_layers():
    problems = _violations()
    assert not problems, "Upward imports found:\n  " + "\n  ".join(problems)


def test_nothing_imports_the_app_entry_point():
    importers = [
        _module_name(p) for p in APP.rglob("*.py") if p.name != "main.py" and "app.main" in _imports(p)
    ]
    assert not importers, f"Import shared objects from their own module, not app.main: {importers}"


@pytest.mark.parametrize("package", sorted(p.name for p in (APP / "services").iterdir() if p.is_dir() and not p.name.startswith("_")))
def test_every_service_package_says_what_it_is_for(package):
    init = APP / "services" / package / "__init__.py"
    assert init.exists() and ast.get_docstring(ast.parse(init.read_text())), f"services/{package}/__init__.py needs a docstring"
