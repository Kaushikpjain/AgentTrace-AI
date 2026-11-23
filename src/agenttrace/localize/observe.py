"""Observable-trace helpers shared by localizers (no privileged data)."""

from __future__ import annotations

from typing import Any

from agenttrace.trace.schema import Boundary, Event, Trace


def boundary_events(trace: Trace) -> list[Event]:
    return [e for e in trace.events if e.boundary in (Boundary.DECISION, Boundary.TOOL)]


def symptom_seq(trace: Trace) -> int:
    """The visible failure point: the last committed mutating tool event; else the last tool
    event; else the last event."""
    tools = [e for e in trace.events if e.boundary is Boundary.TOOL]
    committed = [e for e in tools if e.state is not None and e.state.committed]
    if committed:
        return committed[-1].seq
    if tools:
        return tools[-1].seq
    return trace.events[-1].seq


def _scalars(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {s for v in value.values() for s in _scalars(v)}
    if isinstance(value, list):
        return {s for v in value for s in _scalars(v)}
    if isinstance(value, bool) or value is None:
        return set()
    text = str(value)
    return {text} if len(text) >= 2 else set()


def symptom_chain(trace: Trace, symptom: int) -> set[int]:
    """Taint-style argument-origin chain (standard technique; PLAN §11.2 B3).

    The symptom event, the decision that issued it, and earlier tool events whose delivered
    responses contain a scalar value used verbatim in the symptom's arguments.
    """
    events = {e.seq: e for e in trace.events}
    target = events[symptom]
    chain = {symptom}
    decisions = [
        e
        for e in trace.events
        if e.boundary is Boundary.DECISION and e.seq < symptom and e.step_index == target.step_index
    ]
    if decisions:
        chain.add(decisions[-1].seq)
    request = target.request if isinstance(target.request, dict) else {}
    values = _scalars(request.get("args", {}))
    for event in trace.events:
        if event.seq >= symptom or event.boundary is not Boundary.TOOL:
            continue
        response = event.response if isinstance(event.response, dict) else {}
        if values & _scalars(response.get("data")):
            chain.add(event.seq)
    return chain


def tool_index_at_or_after(trace: Trace, seq: int) -> int | None:
    """Index (0-based) among tool events of the first tool event with seq >= ``seq``."""
    tools = [e.seq for e in trace.events if e.boundary is Boundary.TOOL]
    for index, tool_seq in enumerate(tools):
        if tool_seq >= seq:
            return index
    return None
