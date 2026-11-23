"""BoundaryGateway: the single choke point for decisions and tool calls.

Implements the tool lifecycle S1-S7 and decision lifecycle D1-D4 of REPLAY_SPEC.md
sections 3-4. It owns the live environment state; tools only ever see working copies.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from agenttrace.env.base import ToolResult, ToolSpec
from agenttrace.env.delta import json_diff
from agenttrace.runtime.faults import DecisionContext, FaultHook, ToolContext
from agenttrace.runtime.types import Decision, Observation, Policy, ToolResponse
from agenttrace.trace.canonical import to_json_value
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.ids import new_span_id
from agenttrace.trace.schema import (
    Boundary,
    DeltaOp,
    Divergence,
    Event,
    EventStatus,
    FaultApplication,
    LedgerEntry,
    StateTransition,
)


class ReadOnlyToolMutatedState(RuntimeError):
    """A tool declared read-only changed its working copy (programming error; aborts the run)."""


class DivergenceDetected(Exception):
    """Raised by replaying gateways to end the run at the first divergence (fail closed)."""

    def __init__(self, divergence: Divergence) -> None:
        super().__init__(f"{divergence.kind} at seq {divergence.seq}: {divergence.detail}")
        self.divergence = divergence


def _validation_message(exc: ValidationError) -> str:
    """Deterministic, input-free summary of validation errors."""
    parts = sorted(
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['type']}"
        for err in exc.errors(include_url=False, include_input=False)
    )
    return "; ".join(parts)


def _to_response(result: ToolResult) -> ToolResponse:
    if result.ok:
        return ToolResponse.ok(result.data)
    return ToolResponse.error_response(result.error_code or "ERROR", result.message or "")


def _dump(model: BaseModel) -> Any:
    return to_json_value(model)


@dataclass(frozen=True)
class ToolExecution[S: BaseModel]:
    """Result of lifecycle stages S1-S4 (before post-execution faults)."""

    state: S  # resulting state (the working copy if committed, else the input state)
    before_hash: str
    after_hash: str
    executed: bool
    committed: bool
    delta: tuple[DeltaOp, ...]
    raw: ToolResponse | None  # raw tool result; None if not executed
    response: ToolResponse  # input to S5 (raw, or the S1/S2 response)
    pre_applications: tuple[FaultApplication, ...]


class BoundaryGateway[S: BaseModel]:
    def __init__(
        self,
        *,
        run_id: str,
        state: S,
        tools: Mapping[str, ToolSpec[Any]],
        fault_hook: FaultHook,
    ) -> None:
        self._run_id = run_id
        self._state = state
        self._tools = tools
        self._hook = fault_hook
        self._events: list[Event] = []
        self._ledger: list[LedgerEntry] = []
        self._occurrences: Counter[tuple[Boundary, str]] = Counter()
        self._request_counts: Counter[str] = Counter()

    # ------------------------------------------------------------------ accessors
    @property
    def state(self) -> S:
        return self._state

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    @property
    def ledger(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._ledger)

    def state_hash(self) -> str:
        return fingerprint(self._state)

    # ------------------------------------------------------------------ helpers
    def _next(self, boundary: Boundary, name: str, step_index: int) -> tuple[int, str, int]:
        self._occurrences[(boundary, name)] += 1
        occurrence = self._occurrences[(boundary, name)]
        seq = len(self._events)
        return seq, f"{step_index}:{boundary.value}:{name}#{occurrence}", occurrence

    # ------------------------------------------------------------------ AGENT_STEP span
    def open_step(self, step_index: int) -> str:
        seq, key, _ = self._next(Boundary.AGENT_STEP, "step", step_index)
        span_id = new_span_id()
        self._events.append(
            Event(
                span_id=span_id,
                run_id=self._run_id,
                seq=seq,
                step_index=step_index,
                logical_key=key,
                boundary=Boundary.AGENT_STEP,
                name="step",
                status=EventStatus.OK,
            )
        )
        return span_id

    # ------------------------------------------------------------------ D1-D4
    def decide[T: BaseModel](
        self,
        policy: Policy[T],
        task: T,
        history: Sequence[Observation],
        *,
        step_index: int,
        parent_span_id: str,
    ) -> Decision:
        seq, key, occurrence = self._next(Boundary.DECISION, "decide", step_index)
        request = {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "history_fp": fingerprint([_dump(obs) for obs in history]),
        }
        raw, delivered, applications = self._produce_decision(
            DecisionContext(seq=seq, step_index=step_index, occurrence=occurrence),
            fingerprint(request),
            policy,
            task,
            history,
        )
        raw_json, delivered_json = _dump(raw), _dump(delivered)
        self._events.append(  # D4 (observable)
            Event(
                span_id=new_span_id(),
                parent_span_id=parent_span_id,
                run_id=self._run_id,
                seq=seq,
                step_index=step_index,
                logical_key=key,
                boundary=Boundary.DECISION,
                name="decide",
                status=EventStatus.OK,
                request=request,
                request_fp=fingerprint(request),
                response=delivered_json,
                response_fp=fingerprint(delivered_json),
                intervened=self._is_intervened(seq),
            )
        )
        self._ledger.append(  # D4 (privileged)
            LedgerEntry(
                seq=seq,
                boundary=Boundary.DECISION,
                raw_output=raw_json,
                raw_output_fp=fingerprint(raw_json),
                fault_applications=tuple(applications),
            )
        )
        return delivered  # D3

    def _produce_decision[T: BaseModel](
        self,
        ctx: DecisionContext,
        request_fp: str,
        policy: Policy[T],
        task: T,
        history: Sequence[Observation],
    ) -> tuple[Decision, Decision, list[FaultApplication]]:
        """D1-D2: (raw, delivered, fault applications). Replaying gateways override this."""
        raw = policy.decide(task, history)  # D1
        delivered, applications = self._hook.on_decision(ctx, raw)  # D2
        return raw, delivered, list(applications)

    # ------------------------------------------------------------------ replay seams
    def _before_tool(self, seq: int, name: str, request_fp: str) -> None:
        """Called after the request is formed and before any execution (no-op in RECORD)."""

    def _after_tool(self, event: Event, entry: LedgerEntry) -> None:
        """Called after the event and ledger entry are recorded (no-op in RECORD)."""

    def finish(self) -> None:
        """Called when the agent loop ends normally (no-op in RECORD)."""

    # ------------------------------------------------------------------ S1-S7
    def lifecycle(
        self, name: str, args: Any, ctx: ToolContext, hook: FaultHook, state: S
    ) -> ToolExecution[S]:
        """S1-S4 against ``state`` (never mutated): validate, pre-execution faults, execute on a
        working copy, commit/roll back. Returns the resulting state without installing it."""
        before_hash = fingerprint(state)
        spec = self._tools.get(name)
        if spec is None:  # S1
            response = ToolResponse.error_response("UNKNOWN_TOOL", f"unknown tool {name!r}")
            return ToolExecution(
                state, before_hash, before_hash, False, False, (), None, response, ()
            )
        try:
            parsed = spec.args_model.model_validate(args)
        except ValidationError as exc:
            response = ToolResponse.error_response("INVALID_ARGUMENTS", _validation_message(exc))
            return ToolExecution(
                state, before_hash, before_hash, False, False, (), None, response, ()
            )
        prevented, pre_apps = hook.pre_execution(ctx)  # S2
        if prevented is not None:
            return ToolExecution(
                state, before_hash, before_hash, False, False, (), None, prevented, tuple(pre_apps)
            )
        working = state.model_copy(deep=True)  # S3 (isolated working copy)
        try:
            result = spec.fn(working, parsed)
        except Exception as exc:  # tool bug -> structured error, no commit
            result = ToolResult.failure("TOOL_EXCEPTION", type(exc).__name__)
        raw = _to_response(result)
        working_hash = fingerprint(working)
        if spec.mutating:  # S4
            if result.ok and working_hash != before_hash:
                delta = tuple(json_diff(to_json_value(state), to_json_value(working)))
                return ToolExecution(
                    working, before_hash, working_hash, True, True, delta, raw, raw, tuple(pre_apps)
                )
        elif working_hash != before_hash:
            raise ReadOnlyToolMutatedState(f"read-only tool {name!r} mutated state")
        return ToolExecution(
            state, before_hash, before_hash, True, False, (), raw, raw, tuple(pre_apps)
        )

    def _tool_hook(self, seq: int) -> FaultHook:
        """Fault hook for this tool event (counterfactual replay may disable it at the target)."""
        return self._hook

    def _transform_delivered(
        self, seq: int, ctx: ToolContext, delivered: ToolResponse, execution: ToolExecution[S]
    ) -> ToolResponse:
        """After S5: counterfactual OBSERVATION_REPLACEMENT replaces the delivered value here."""
        return delivered

    def _is_intervened(self, seq: int) -> bool:
        return False

    def call_tool(
        self, decision: Decision, *, step_index: int, parent_span_id: str
    ) -> ToolResponse:
        if decision.kind != "tool_call" or decision.tool is None:
            raise ValueError("call_tool requires a tool_call decision")
        name = decision.tool
        args = decision.args
        seq, key, occurrence = self._next(Boundary.TOOL, name, step_index)
        request = {"tool": name, "args": args}
        request_fp = fingerprint(request)
        self._before_tool(seq, name, request_fp)
        self._request_counts[request_fp] += 1
        attempt = self._request_counts[request_fp]
        ctx = ToolContext(
            seq=seq,
            step_index=step_index,
            tool=name,
            args=args,
            occurrence=occurrence,
            attempt=attempt,
        )
        hook = self._tool_hook(seq)
        execution = self.lifecycle(name, args, ctx, hook, self._state)  # S1-S4
        self._state = execution.state  # atomic commit (single reference swap) or unchanged
        delivered, post_apps = hook.post_execution(ctx, execution.response)  # S5
        delivered = self._transform_delivered(seq, ctx, delivered, execution)
        applications = (*execution.pre_applications, *post_apps)
        delivered_json = _dump(delivered)
        raw_json = _dump(execution.raw) if execution.raw is not None else None

        event = Event(
            span_id=new_span_id(),
            parent_span_id=parent_span_id,
            run_id=self._run_id,
            seq=seq,
            step_index=step_index,
            logical_key=key,
            boundary=Boundary.TOOL,
            name=name,
            status=delivered.status,
            request=request,
            request_fp=request_fp,
            response=delivered_json,
            response_fp=fingerprint(delivered_json),
            state=StateTransition(
                before_hash=execution.before_hash,
                after_hash=execution.after_hash,
                committed=execution.committed,
                delta=execution.delta,
            ),
            attempt=attempt,
            intervened=self._is_intervened(seq),
        )
        entry = LedgerEntry(
            seq=seq,
            boundary=Boundary.TOOL,
            executed=execution.executed,
            raw_output=raw_json,
            raw_output_fp=fingerprint(raw_json) if raw_json is not None else None,
            fault_applications=applications,
        )
        self._events.append(event)  # S6/S7 (observable)
        self._ledger.append(entry)  # S7 (privileged)
        self._after_tool(event, entry)
        return delivered
