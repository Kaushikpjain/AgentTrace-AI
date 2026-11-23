"""SHA-256 fingerprints over canonical JSON (TRACE_SCHEMA.md section 6)."""

from __future__ import annotations

import hashlib
from typing import Any

from agenttrace.trace.canonical import canonical_bytes

PREFIX = "sha256:"


def fingerprint(value: Any) -> str:
    """Return ``"sha256:<hex>"`` of the canonical JSON encoding of ``value``."""
    return PREFIX + hashlib.sha256(canonical_bytes(value)).hexdigest()


def fingerprint_text(text: str) -> str:
    """Fingerprint raw text (e.g. module source code) without JSON encoding."""
    return PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()
