"""Hash chain over events and ledger entries (TRACE_SCHEMA.md section 7).

Detects accidental corruption and truncation. It is NOT a security control.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from agenttrace.trace.canonical import canonical_bytes
from agenttrace.trace.schema import Event, LedgerEntry

_CHAIN_SEED = b"agenttrace-chain-v1"


def compute_chain_root(events: Iterable[Event], ledger: Iterable[LedgerEntry]) -> str:
    digest = hashlib.sha256(_CHAIN_SEED).digest()
    for record in (*events, *ledger):
        digest = hashlib.sha256(digest + canonical_bytes(record)).digest()
    return digest.hex()
