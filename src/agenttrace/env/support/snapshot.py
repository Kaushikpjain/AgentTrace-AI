"""Snapshot, restore and hash for SupportState.

Snapshot = canonical JSON bytes; restore = parse into a brand-new object (no shared
references); hash = fingerprint of the canonical form.
"""

from __future__ import annotations

import json

from agenttrace.env.support.models import SupportState
from agenttrace.trace.canonical import canonical_bytes
from agenttrace.trace.fingerprint import fingerprint


def snapshot(state: SupportState) -> bytes:
    return canonical_bytes(state)


def restore(data: bytes) -> SupportState:
    return SupportState.model_validate(json.loads(data))


def state_hash(state: SupportState) -> str:
    return fingerprint(state)


def working_copy(state: SupportState) -> SupportState:
    """Deep, independent copy for transactional tool execution."""
    return state.model_copy(deep=True)
