"""Static guards: environment and policy code must be deterministic and side-effect free."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "agenttrace"
BANNED = {
    "random",
    "time",
    "uuid",
    "datetime",
    "secrets",
    "subprocess",
    "socket",
    "os",
    "shutil",
    "requests",
    "httpx",
    "urllib",
    "http",
    "asyncio",
    "threading",
    "multiprocessing",
    "agenttrace.trace.ids",
}
GUARDED_DIRS = ["env", "policies", "faults"]


def _modules() -> list[Path]:
    return sorted(p for d in GUARDED_DIRS for p in (SRC / d).rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_nondeterministic_or_io_imports(path: Path) -> None:
    offending = {
        name
        for name in _imports(path)
        if any(name == banned or name.startswith(banned + ".") for banned in BANNED)
    }
    assert not offending, f"{path.relative_to(SRC)} imports {sorted(offending)}"


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_eval_exec_or_open(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls & {"eval", "exec", "open", "__import__", "compile"}


def test_guard_covers_expected_modules() -> None:
    names = {str(p.relative_to(SRC)) for p in _modules()}
    assert {"env/support/tools.py", "policies/support_scripted.py"} <= names
