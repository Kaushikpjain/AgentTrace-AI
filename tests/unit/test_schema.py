from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from agenttrace.trace.canonical import canonical_bytes
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import (
    Boundary,
    Event,
    EventStatus,
    Intervention,
    InterventionType,
    LedgerEntry,
    ReferenceSource,
    RunHeader,
    RunMode,
    StateTransition,
    UnsupportedSchemaVersion,
    check_schema_version,
)
from agenttrace.trace.semantic import semantic_fingerprint
from tests.helpers import make_header, make_record


def test_record_roundtrips_through_canonical_json() -> None:
    record = make_record()
    again = type(record).model_validate_json(canonical_bytes(record))
    assert again == record
    assert canonical_bytes(again) == canonical_bytes(record)


def test_payload_decimals_normalized_at_construction() -> None:
    payload = {"amount": Decimal("80.00")}
    event = Event(
        span_id="x",
        run_id="r",
        seq=0,
        step_index=0,
        logical_key="k",
        boundary=Boundary.DECISION,
        name="decide",
        status=EventStatus.OK,
        request=payload,
        request_fp=fingerprint(payload),
    )
    assert event.request == {"amount": "80"}


def test_floats_rejected_in_payloads() -> None:
    with pytest.raises(ValidationError):
        Event(
            span_id="x",
            run_id="r",
            seq=0,
            step_index=0,
            logical_key="k",
            boundary=Boundary.DECISION,
            name="decide",
            status=EventStatus.OK,
            request={"a": 1.5},
            request_fp="sha256:0",
        )


def test_request_fp_must_match() -> None:
    with pytest.raises(ValidationError, match="request_fp"):
        Event(
            span_id="x",
            run_id="r",
            seq=0,
            step_index=0,
            logical_key="k",
            boundary=Boundary.DECISION,
            name="decide",
            status=EventStatus.OK,
            request={"a": 1},
            request_fp=fingerprint({"a": 2}),
        )


def test_tool_event_requires_state_and_attempt() -> None:
    with pytest.raises(ValidationError, match="TOOL events require"):
        Event(
            span_id="x",
            run_id="r",
            seq=0,
            step_index=0,
            logical_key="k",
            boundary=Boundary.TOOL,
            name="get_order",
            status=EventStatus.OK,
        )


def test_state_transition_constraints() -> None:
    StateTransition(before_hash="h1", after_hash="h1", committed=False)
    with pytest.raises(ValidationError):
        StateTransition(before_hash="h1", after_hash="h2", committed=False)
    with pytest.raises(ValidationError):
        StateTransition(before_hash="h1", after_hash="h1", committed=True)


def test_ledger_rules() -> None:
    with pytest.raises(ValidationError, match="non-executed"):
        LedgerEntry(
            seq=0,
            boundary=Boundary.TOOL,
            executed=False,
            raw_output={"a": 1},
            raw_output_fp=fingerprint({"a": 1}),
        )
    with pytest.raises(ValidationError, match="executed"):
        LedgerEntry(seq=0, boundary=Boundary.TOOL)
    with pytest.raises(ValidationError, match="only for DECISION and TOOL"):
        LedgerEntry(seq=0, boundary=Boundary.AGENT_STEP)


def test_header_config_fingerprint_validated() -> None:
    header = make_header()
    data = header.model_dump()
    data["max_steps"] = 99
    with pytest.raises(ValidationError, match="config_fingerprint"):
        RunHeader.model_validate(data)


def test_header_intervention_only_in_intervene_mode() -> None:
    header = make_header()
    intervention = Intervention(
        target_seq=2,
        target_logical_key="0:TOOL:x#1",
        boundary=Boundary.TOOL,
        intervention_type=InterventionType.EXECUTION_REPLACEMENT,
        reference_source=ReferenceSource.REFERENCE_TOOL,
        is_placebo=False,
        replacement_fp="sha256:0",
        expected_semantics="clean execution",
    )
    data = header.model_dump()
    data["intervention"] = intervention.model_dump()
    with pytest.raises(ValidationError, match="intervention"):
        RunHeader.model_validate(data)
    data["mode"] = RunMode.REPLAY_INTERVENE
    assert RunHeader.model_validate(data).intervention == intervention


def test_extra_fields_forbidden() -> None:
    data = make_header().model_dump()
    data["unexpected"] = 1
    with pytest.raises(ValidationError):
        RunHeader.model_validate(data)


@pytest.mark.parametrize("version", ["1.0", "1.7"])
def test_supported_versions(version: str) -> None:
    check_schema_version(version)


@pytest.mark.parametrize("version", ["2.0", "0.9", "1", "x.y"])
def test_unsupported_versions(version: str) -> None:
    with pytest.raises(UnsupportedSchemaVersion):
        check_schema_version(version)


def test_semantic_fingerprint_ignores_execution_specific_fields() -> None:
    a = make_record("run-a")
    b = make_record("run-b")
    assert a.header.run_id != b.header.run_id
    assert semantic_fingerprint(a) == semantic_fingerprint(b)


def test_semantic_fingerprint_sensitive_to_content() -> None:
    a = make_record()
    events = list(a.events)
    events[0] = events[0].model_copy(update={"step_index": 1})
    b = a.model_copy(update={"events": tuple(events)})
    assert semantic_fingerprint(a) != semantic_fingerprint(b)
