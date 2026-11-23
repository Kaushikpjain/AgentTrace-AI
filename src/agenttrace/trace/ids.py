"""Execution-specific identifiers and timestamps (ADR-008).

These values differ between executions by design and are excluded from semantic
fingerprints. Environment and policy code must never import this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_run_id() -> str:
    """Return a sortable, unique run identifier, e.g. ``run-20261123T101500Z-1a2b3c4d``."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{stamp}-{uuid.uuid4().hex[:8]}"


def new_span_id() -> str:
    """Return a unique span identifier."""
    return uuid.uuid4().hex


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)
