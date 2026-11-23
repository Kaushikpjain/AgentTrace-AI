"""Trace schema v1.0 (authoritative contract: docs/TRACE_SCHEMA.md).

Observable trace: RunHeader, Event, RunFooter (readable by localizers).
Privileged ledger: LedgerEntry / FaultApplication (replay engine + benchmark validator only).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from agenttrace.trace.canonical import JsonValue, to_json_value
from agenttrace.trace.fingerprint import fingerprint

SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_MAJOR = 1


def _json_pure(value: Any) -> JsonValue:
    """Normalize a payload to JSON-pure values (Decimals -> strings, floats rejected)."""
    return to_json_value(value)


JsonPayload = Annotated[Any, AfterValidator(_json_pure)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- enums


class RunMode(StrEnum):
    RECORD = "RECORD"
    REPLAY_STRICT = "REPLAY_STRICT"
    REPLAY_INTERVENE = "REPLAY_INTERVENE"
    REGRESSION = "REGRESSION"


class RunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    MAX_STEPS = "MAX_STEPS"
    DIVERGED = "DIVERGED"
    INVALID_COUNTERFACTUAL = "INVALID_COUNTERFACTUAL"
    UNSUPPORTED = "UNSUPPORTED"
    CONFIG_MISMATCH = "CONFIG_MISMATCH"
    INTERRUPTED = "INTERRUPTED"


class Outcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class Boundary(StrEnum):
    AGENT_STEP = "AGENT_STEP"
    DECISION = "DECISION"
    TOOL = "TOOL"
    CLOCK = "CLOCK"  # reserved (ADR-008)
    IDGEN = "IDGEN"  # reserved (ADR-008)


class EventStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class FaultStage(StrEnum):
    DECISION = "DECISION"
    PRE_EXECUTION = "PRE_EXECUTION"
    POST_EXECUTION = "POST_EXECUTION"


class FaultEffect(StrEnum):
    PREVENTED_EXECUTION = "prevented_execution"
    TRANSFORMED_OUTPUT = "transformed_output"


class InterventionType(StrEnum):
    OBSERVATION_REPLACEMENT = "OBSERVATION_REPLACEMENT"
    EXECUTION_REPLACEMENT = "EXECUTION_REPLACEMENT"


class ReferenceSource(StrEnum):
    REFERENCE_TOOL = "REFERENCE_TOOL"
    REFERENCE_POLICY = "REFERENCE_POLICY"
    ORIGINAL = "ORIGINAL"
    INJECTION_CLEAN_VALUE = "INJECTION_CLEAN_VALUE"  # benchmark validator only


class DivergenceKind(StrEnum):
    MISSING_EVENT = "MISSING_EVENT"
    TRUNCATED = "TRUNCATED"
    BOUNDARY = "BOUNDARY"
    NAME = "NAME"
    REQUEST = "REQUEST"
    RAW_RESULT = "RAW_RESULT"
    STATE = "STATE"
    RESPONSE = "RESPONSE"
    OUTCOME = "OUTCOME"


# --------------------------------------------------------------------------- header


class ScenarioRef(_Model):
    id: str
    version: str
    initial_state_hash: str


class AgentRef(_Model):
    policy_id: str
    policy_version: str
    source_hash: str


class OracleRef(_Model):
    id: str
    version: str


class Intervention(_Model):
    target_seq: int = Field(ge=0)
    target_logical_key: str
    boundary: Boundary
    intervention_type: InterventionType
    reference_source: ReferenceSource
    is_placebo: bool
    replacement_fp: str
    expected_semantics: str


def compute_config_fingerprint(
    *,
    schema_version: str,
    scenario: ScenarioRef,
    agent: AgentRef,
    tool_manifest_hash: str,
    fault_plan_hash: str | None,
    oracle: OracleRef,
    max_steps: int,
) -> str:
    """Configuration fingerprint (REPLAY_SPEC.md section 8)."""
    return fingerprint(
        {
            "schema_version": schema_version,
            "scenario": scenario,
            "agent": agent,
            "tool_manifest_hash": tool_manifest_hash,
            "fault_plan_hash": fault_plan_hash,
            "oracle": oracle,
            "max_steps": max_steps,
        }
    )


class RunHeader(_Model):
    schema_version: str = SCHEMA_VERSION
    run_id: str
    mode: RunMode
    parent_run_id: str | None = None
    scenario: ScenarioRef
    agent: AgentRef
    tool_manifest_hash: str
    fault_plan_hash: str | None = None
    oracle: OracleRef
    max_steps: int = Field(ge=1)
    config_fingerprint: str
    intervention: Intervention | None = None
    started_at: AwareDatetime
    agenttrace_version: str

    @model_validator(mode="after")
    def _check(self) -> Self:
        check_schema_version(self.schema_version)
        expected = compute_config_fingerprint(
            schema_version=self.schema_version,
            scenario=self.scenario,
            agent=self.agent,
            tool_manifest_hash=self.tool_manifest_hash,
            fault_plan_hash=self.fault_plan_hash,
            oracle=self.oracle,
            max_steps=self.max_steps,
        )
        if self.config_fingerprint != expected:
            raise ValueError("config_fingerprint does not match header fields")
        if (self.mode is RunMode.REPLAY_INTERVENE) != (self.intervention is not None):
            raise ValueError("intervention must be present iff mode is REPLAY_INTERVENE")
        return self


class UnsupportedSchemaVersion(ValueError):
    """Raised for a schema major version this code cannot read."""


def check_schema_version(version: str) -> None:
    major, _, minor = version.partition(".")
    if not (major.isdigit() and minor.isdigit()):
        raise UnsupportedSchemaVersion(f"malformed schema_version: {version!r}")
    if int(major) != SUPPORTED_SCHEMA_MAJOR:
        raise UnsupportedSchemaVersion(
            f"schema major {major} not supported (expected {SUPPORTED_SCHEMA_MAJOR}.x)"
        )


# --------------------------------------------------------------------------- events


class DeltaOp(_Model):
    op: Literal["add", "remove", "replace"]
    path: str
    old: JsonPayload = None
    new: JsonPayload = None


class StateTransition(_Model):
    before_hash: str
    after_hash: str
    committed: bool
    delta: tuple[DeltaOp, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.committed != (self.before_hash != self.after_hash):
            raise ValueError("committed must be true iff before_hash != after_hash")
        if self.committed != bool(self.delta):
            raise ValueError("delta must be non-empty iff committed")
        return self


class Event(_Model):
    span_id: str
    parent_span_id: str | None = None
    run_id: str
    seq: int = Field(ge=0)
    step_index: int = Field(ge=0)
    logical_key: str
    boundary: Boundary
    name: str
    status: EventStatus
    request: JsonPayload = None
    request_fp: str | None = None
    response: JsonPayload = None
    response_fp: str | None = None
    state: StateTransition | None = None
    attempt: int | None = Field(default=None, ge=1)
    intervened: bool = False

    @model_validator(mode="after")
    def _check(self) -> Self:
        for payload, fp_value, label in (
            (self.request, self.request_fp, "request"),
            (self.response, self.response_fp, "response"),
        ):
            if fp_value is None:
                if payload is not None:
                    raise ValueError(f"{label}_fp missing for non-null {label}")
            elif fp_value != fingerprint(payload):
                raise ValueError(f"{label}_fp does not match {label} payload")
        is_tool = self.boundary is Boundary.TOOL
        if is_tool and (self.state is None or self.attempt is None):
            raise ValueError("TOOL events require state and attempt")
        if not is_tool and (self.state is not None or self.attempt is not None):
            raise ValueError("only TOOL events may carry state/attempt")
        return self


# --------------------------------------------------------------------------- ledger


class FaultApplication(_Model):
    fault_id: str
    operator: str
    stage: FaultStage
    effect: FaultEffect
    input_fp: str | None = None
    output_fp: str


class LedgerEntry(_Model):
    seq: int = Field(ge=0)
    boundary: Boundary
    executed: bool | None = None
    raw_output: JsonPayload = None
    raw_output_fp: str | None = None
    fault_applications: tuple[FaultApplication, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.raw_output_fp is None:
            if self.raw_output is not None:
                raise ValueError("raw_output_fp missing for non-null raw_output")
        elif self.raw_output_fp != fingerprint(self.raw_output):
            raise ValueError("raw_output_fp does not match raw_output")
        if self.boundary not in (Boundary.DECISION, Boundary.TOOL):
            raise ValueError("ledger entries exist only for DECISION and TOOL boundaries")
        if self.boundary is Boundary.TOOL and self.executed is None:
            raise ValueError("TOOL ledger entries require executed")
        if self.boundary is Boundary.DECISION and self.executed is not None:
            raise ValueError("DECISION ledger entries must not set executed")
        if self.executed is False and self.raw_output is not None:
            raise ValueError("a non-executed tool call cannot have a raw output")
        return self


# --------------------------------------------------------------------------- footer


class ViolatedClause(_Model):
    clause_id: str
    message: str
    symptom_seq: int | None = None


class OutcomeRecord(_Model):
    outcome: Outcome
    violated_clauses: tuple[ViolatedClause, ...] = ()


class Totals(_Model):
    events: int = Field(ge=0)
    decisions: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    steps: int = Field(ge=0)


class Divergence(_Model):
    seq: int = Field(ge=0)
    kind: DivergenceKind
    expected_fp: str | None = None
    actual_fp: str | None = None
    detail: str


class Integrity(_Model):
    event_count: int = Field(ge=0)
    ledger_count: int = Field(ge=0)
    chain_root: str


class RunFooter(_Model):
    status: RunStatus
    outcome: OutcomeRecord
    final_state_hash: str
    totals: Totals
    divergence: Divergence | None = None
    ended_at: AwareDatetime
    wall_ms: int = Field(ge=0)
    integrity: Integrity


# --------------------------------------------------------------------------- containers


class Trace(_Model):
    """Observable trace: what localizers may read."""

    header: RunHeader
    events: tuple[Event, ...]
    footer: RunFooter


class RunRecord(_Model):
    """Complete recording, including the privileged ledger."""

    header: RunHeader
    events: tuple[Event, ...]
    ledger: tuple[LedgerEntry, ...]
    footer: RunFooter

    def observable(self) -> Trace:
        return Trace(header=self.header, events=self.events, footer=self.footer)
