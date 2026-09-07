"""The architecture claim, enforced.

The core must stay forge-agnostic and cloud-agnostic, and a provider must stay
forge-agnostic. If either stops being true this test fails, which is the only way
the promise survives contact with a second forge or a second cloud.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "iac_review"


def _imports(package: Path) -> dict[Path, set[str]]:
    found: dict[Path, set[str]] = {}
    for path in sorted(package.rglob("*.py")):
        names: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module)
        found[path] = names
    return found


@pytest.mark.parametrize("banned", ["iac_review.forges", "iac_review.providers"])
def test_core_imports_neither_forges_nor_providers(banned: str) -> None:
    offenders = {
        path.name: sorted(n for n in names if n.startswith(banned))
        for path, names in _imports(SRC / "core").items()
        if any(n.startswith(banned) for n in names)
    }
    assert not offenders, f"core imported {banned}: {offenders}"


def test_providers_do_not_import_forges() -> None:
    offenders = {
        path.name: sorted(n for n in names if n.startswith("iac_review.forges"))
        for path, names in _imports(SRC / "providers").items()
        if any(n.startswith("iac_review.forges") for n in names)
    }
    assert not offenders, f"a provider imported a forge: {offenders}"


def test_forges_do_not_import_providers() -> None:
    offenders = {
        path.name: sorted(n for n in names if n.startswith("iac_review.providers"))
        for path, names in _imports(SRC / "forges").items()
        if any(n.startswith("iac_review.providers") for n in names)
    }
    assert not offenders, f"a forge imported a provider: {offenders}"
