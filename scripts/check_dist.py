"""Inspect built distributions for content that must not ship (ADR-030).

Usage: python scripts/check_dist.py <dist-dir>
Exit 0 when every wheel/sdist in <dist-dir> passes, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_PATHS = (
    re.compile(r"(^|/)docs/PLAN_v0\.2\.1\.md$"),
    re.compile(r"(^|/)docs/archive/"),
    re.compile(r"(^|/)docs/PHASE2_PLAN\.md$"),
    re.compile(r"(^|/)docs/WEEK4_PLAN\.md$"),
    re.compile(r"(^|/)private/"),
    re.compile(r"(^|/)experiments/"),
    re.compile(r"(^|/)\.env"),
    re.compile(r"\.(gguf|safetensors|bin)$"),
)
FORBIDDEN_TEXT = (
    re.compile(rb"/Users/[A-Za-z]"),
    re.compile(rb"/home/[A-Za-z]"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}"),
)
REQUIRED_IN_WHEEL = tuple(f"agenttrace/env/support/scenarios/T{i}.json" for i in range(1, 9))


def _members(path: Path) -> dict[str, bytes]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as zf:
            return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    with tarfile.open(path) as tf:
        out: dict[str, bytes] = {}
        for m in tf.getmembers():
            if m.isfile():
                f = tf.extractfile(m)
                if f is not None:
                    out[m.name.split("/", 1)[1] if "/" in m.name else m.name] = f.read()
        return out


def check(path: Path) -> list[str]:
    members = _members(path)
    problems = [
        f"{path.name}: forbidden file {name}"
        for name in members
        if any(p.search(name) for p in FORBIDDEN_PATHS)
    ]
    for name, data in members.items():
        for pattern in FORBIDDEN_TEXT:
            if pattern.search(data):
                problems.append(f"{path.name}: {name} matches {pattern.pattern!r}")
    if path.suffix == ".whl":
        problems += [f"{path.name}: missing {r}" for r in REQUIRED_IN_WHEEL if r not in members]
    print(f"{path.name}: {len(members)} files, {len(problems)} problems")
    return problems


def main(argv: list[str]) -> int:
    dists = sorted(Path(argv[1]).glob("*.whl")) + sorted(Path(argv[1]).glob("*.tar.gz"))
    if not dists:
        print("no distributions found")
        return 1
    problems = [p for d in dists for p in check(d)]
    for problem in problems:
        print(f"  - {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
