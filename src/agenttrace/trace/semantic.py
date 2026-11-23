"""Semantic fingerprints: run identity with execution-specific fields removed.

Excluded (TRACE_SCHEMA.md section 6): run_id, parent_run_id, started_at,
agenttrace_version, span_id, parent_span_id (replaced by parent seq), ended_at,
wall_ms, integrity.
"""

from __future__ import annotations

from typing import Any

from agenttrace.trace.canonical import to_json_value
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import RunRecord

_HEADER_EXCLUDE = {"run_id", "parent_run_id", "started_at", "agenttrace_version"}
_FOOTER_EXCLUDE = {"ended_at", "wall_ms", "integrity"}


def semantic_view(record: RunRecord) -> dict[str, Any]:
    span_to_seq = {event.span_id: event.seq for event in record.events}
    events = []
    for event in record.events:
        data = event.model_dump(mode="python", exclude={"span_id", "parent_span_id", "run_id"})
        data["parent_seq"] = (
            span_to_seq.get(event.parent_span_id) if event.parent_span_id is not None else None
        )
        events.append(data)
    return {
        "header": record.header.model_dump(mode="python", exclude=_HEADER_EXCLUDE),
        "events": events,
        "ledger": [entry.model_dump(mode="python") for entry in record.ledger],
        "footer": record.footer.model_dump(mode="python", exclude=_FOOTER_EXCLUDE),
    }


def semantic_fingerprint(record: RunRecord) -> str:
    return fingerprint(to_json_value(semantic_view(record)))
