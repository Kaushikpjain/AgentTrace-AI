"""Distribution hygiene (ADR-030): planning/private material is excluded from the sdist."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_sdist_excludes_research_sensitive_and_private_material() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    excluded = set(config["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"])
    for path in (
        "/docs/PLAN_v0.2.1.md",
        "/docs/archive",
        "/docs/PHASE2_PLAN.md",
        "/docs/WEEK4_PLAN.md",
        "/private",
        "/experiments",
    ):
        assert path in excluded, path


def test_wheel_ships_only_the_package() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/agenttrace"]
