"""``atrace`` command-line interface: scenarios, run, show, replay (+ Week 3 commands in
``agenttrace.cli_diagnose``).

Exit codes:
- ``run``: 0 = oracle PASS, 1 = oracle FAIL, 2 = usage or execution error.
- ``replay``: 0 = VERIFIED, 1 = DIVERGED, 2 = usage / run not found,
  3 = CONFIG_MISMATCH, 4 = INTEGRITY_ERROR.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from agenttrace.env.support.scenario import list_scenario_ids, load_scenario
from agenttrace.faults.operators import FaultPlanError
from agenttrace.faults.plan import validate_plan
from agenttrace.policies.support_scripted import PolicyVersion
from agenttrace.replay.exact import ReplayReport, ReplayVerdict, replay_run
from agenttrace.runner import record_scenario, support_replay_context
from agenttrace.trace.schema import Boundary, Event, FaultPlan, Outcome, Trace
from agenttrace.trace.store import JsonlTraceStore, RunNotFoundError, TraceStoreError

app = typer.Typer(
    name="atrace",
    help="AgentTrace AI: record, replay and diagnose tool-using agent runs.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

RunsDir = Annotated[
    Path | None,
    typer.Option("--runs-dir", help="Run store directory (default: $ATRACE_RUNS_DIR or ./runs)."),
]


def _store(runs_dir: Path | None) -> JsonlTraceStore:
    return JsonlTraceStore(runs_dir or Path(os.environ.get("ATRACE_RUNS_DIR", "runs")))


def _short(value: Any, limit: int = 48) -> str:
    """Compact one-line summary: scalar key=value pairs of a dict, or the value itself."""
    if isinstance(value, dict):
        pairs = [f"{k}={v}" for k, v in value.items() if not isinstance(v, dict | list)]
        text = ", ".join(pairs)
    else:
        text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _describe(event: Event) -> tuple[str, str, str]:
    """(action, observed, state) columns for one event."""
    if event.boundary is Boundary.DECISION:
        response = event.response if isinstance(event.response, dict) else {}
        if response.get("kind") == "final":
            return "FINAL", _short(response.get("summary")), ""
        return f"→ {response.get('tool')}", _short(response.get("args")), ""
    if event.boundary is Boundary.TOOL:
        response = event.response if isinstance(event.response, dict) else {}
        observed = response.get("error") or response.get("data")
        state = ""
        if event.state is not None and event.state.committed:
            first = event.state.delta[0].path
            extra = len(event.state.delta) - 1
            state = f"committed {first}" + (f" (+{extra})" if extra else "")
        return event.name, _short(observed), state
    return "", "", ""


def _print_trace(trace: Trace, *, saved_to: Path | None) -> None:
    header, footer = trace.header, trace.footer
    table = Table(
        title=f"{header.scenario.id} · {header.agent.policy_id}:{header.agent.policy_version}"
    )
    for column in ("seq", "step", "boundary", "action", "status", "observed / args", "state"):
        table.add_column(column, overflow="fold")
    for event in trace.events:
        if event.boundary is Boundary.AGENT_STEP:
            continue
        action, observed, state = _describe(event)
        table.add_row(
            str(event.seq),
            str(event.step_index),
            event.boundary.value,
            action,
            event.status.value,
            observed,
            state,
        )
    console.print(table)
    outcome = footer.outcome.outcome
    colour = "green" if outcome is Outcome.PASS else "red"
    console.print(
        f"[bold]Run status:[/bold] {footer.status.value}   "
        f"[bold]Oracle:[/bold] [{colour}]{outcome.value}[/{colour}]"
    )
    for clause in footer.outcome.violated_clauses:
        console.print(f"  [red]✗ {clause.clause_id}[/red]: {clause.message}")
    console.print(f"[bold]Run id:[/bold] {header.run_id}")
    console.print(
        f"[dim]final state {footer.final_state_hash[:23]}…  "
        f"config {header.config_fingerprint[:23]}…[/dim]"
    )
    if saved_to is not None:
        console.print(f"[dim]trace saved to {saved_to}[/dim]")


@app.command("scenarios")
def scenarios_cmd() -> None:
    """List the available scenario templates."""
    table = Table(title="Scenario templates")
    for column in ("id", "split", "scope", "title"):
        table.add_column(column)
    for scenario_id in list_scenario_ids():
        scenario = load_scenario(scenario_id)
        table.add_row(scenario.scenario_id, scenario.split, scenario.scope, scenario.title)
    console.print(table)


@app.command("run")
def run_cmd(
    scenario_id: Annotated[str, typer.Argument(help="Scenario id, e.g. T1")],
    policy: Annotated[
        str, typer.Option("--policy", help="Scripted policy version: v1 or v2")
    ] = "v1",
    runs_dir: RunsDir = None,
    no_save: Annotated[bool, typer.Option("--no-save", help="Do not persist the trace")] = False,
    fault_plan: Annotated[
        Path | None,
        typer.Option("--fault-plan", help="JSON FaultPlan to apply (see examples/fault_plans/)"),
    ] = None,
) -> None:
    """Execute a scenario with the scripted agent and record the trace."""
    if policy not in ("v1", "v2"):
        console.print(f"[red]unknown policy version {policy!r} (use v1 or v2)[/red]")
        raise typer.Exit(2)
    try:
        scenario = load_scenario(scenario_id)
    except KeyError:
        console.print(f"[red]unknown scenario {scenario_id!r}; see `atrace scenarios`[/red]")
        raise typer.Exit(2) from None
    plan: FaultPlan | None = None
    if fault_plan is not None:
        try:
            plan = FaultPlan.model_validate(json.loads(fault_plan.read_text(encoding="utf-8")))
            validate_plan(plan)
        except (OSError, json.JSONDecodeError, ValidationError, FaultPlanError) as exc:
            console.print(f"[red]invalid fault plan {fault_plan}: {exc}[/red]")
            raise typer.Exit(2) from exc
    record = record_scenario(scenario, policy_version=cast(PolicyVersion, policy), fault_plan=plan)
    saved_to: Path | None = None
    if not no_save:
        store = _store(runs_dir)
        try:
            store.save(record)
        except TraceStoreError as exc:
            console.print(f"[red]could not save trace: {exc}[/red]")
            raise typer.Exit(2) from exc
        saved_to = store.root / record.header.run_id
    _print_trace(record.observable(), saved_to=saved_to)
    raise typer.Exit(0 if record.footer.outcome.outcome is Outcome.PASS else 1)


@app.command("show")
def show_cmd(
    run_id: Annotated[str, typer.Argument(help="Run id printed by `atrace run`")],
    runs_dir: RunsDir = None,
) -> None:
    """Load, validate (schema + integrity chain) and display a recorded run."""
    store = _store(runs_dir)
    try:
        trace = store.load_trace(run_id)
    except TraceStoreError as exc:
        console.print(f"[red]{type(exc).__name__}: {exc}[/red]")
        raise typer.Exit(2) from exc
    _print_trace(trace, saved_to=None)
    console.print("[green]integrity verified[/green] (schema, fingerprints, hash chain)")


_REPLAY_EXIT = {
    ReplayVerdict.VERIFIED: 0,
    ReplayVerdict.DIVERGED: 1,
    ReplayVerdict.CONFIG_MISMATCH: 3,
    ReplayVerdict.INTEGRITY_ERROR: 4,
}


def _check(ok: bool) -> str:
    return "[green]✓[/green]" if ok else "[red]✗[/red]"


def _print_replay(report: ReplayReport, saved_to: Path | None) -> None:
    colour = "green" if report.verdict is ReplayVerdict.VERIFIED else "red"
    console.print(
        f"[bold]Strict replay of {report.original_run_id}:[/bold] "
        f"[{colour}]{report.verdict.value}[/{colour}]"
    )
    if report.verdict is ReplayVerdict.INTEGRITY_ERROR:
        console.print(f"  {_check(False)} trace/cassette integrity: {report.integrity_error}")
        return
    console.print(f"  {_check(True)} trace/cassette integrity (schema, fingerprints, hash chain)")
    console.print(f"  {_check(report.config.ok)} configuration matches current code")
    for problem in report.config.mismatches:
        console.print(f"      [red]- {problem}[/red]")
    if report.replay is None:
        return
    console.print(
        f"  {_check(report.policy_calls == 0)} no live policy calls "
        f"(calls={report.policy_calls}); cassette consumed "
        f"{report.cassette_consumed}/{report.cassette_entries}"
    )
    fidelity = report.fidelity
    assert fidelity is not None
    table = Table(title="Replay fidelity (REPLAY_SPEC §11)")
    table.add_column("metric")
    table.add_column("result")
    rows = [
        (
            "delivered responses equal",
            str(fidelity.response_equality),
            fidelity.response_equality.complete,
        ),
        (
            "event sequence agreement",
            str(fidelity.event_sequence),
            fidelity.event_sequence_agreement,
        ),
        (
            "raw tool results equal",
            str(fidelity.raw_result_agreement),
            fidelity.raw_result_agreement.complete,
        ),
        (
            "state transitions equal",
            str(fidelity.state_transition_agreement),
            fidelity.state_transition_agreement.complete,
        ),
        (
            "final state hash equal",
            "yes" if fidelity.final_state_equal else "no",
            fidelity.final_state_equal,
        ),
        (
            "status + oracle outcome equal",
            "yes" if fidelity.outcome_equal else "no",
            fidelity.outcome_equal,
        ),
    ]
    for name, value, ok in rows:
        table.add_row(name, f"{_check(ok)} {value}")
    console.print(table)
    footer = report.replay.footer
    console.print(
        f"  replay status {footer.status.value}, oracle {footer.outcome.outcome.value}; "
        f"final state {footer.final_state_hash[:23]}…"
    )
    if report.divergence is not None:
        d = report.divergence
        console.print(f"[red bold]First divergence:[/red bold] {d.kind.value} at seq {d.seq}")
        console.print(f"  {d.detail}")
        if d.expected_fp or d.actual_fp:
            console.print(f"  expected {d.expected_fp}\n  actual   {d.actual_fp}")
    if saved_to is not None:
        console.print(f"[dim]replay trace saved to {saved_to}[/dim]")


@app.command("replay")
def replay_cmd(
    run_id: Annotated[str, typer.Argument(help="Run id to replay exactly (REPLAY_STRICT)")],
    runs_dir: RunsDir = None,
    policy: Annotated[
        str | None,
        typer.Option("--policy", help="Replay under this policy version (default: recorded)"),
    ] = None,
    save: Annotated[bool, typer.Option("--save", help="Persist the replay trace")] = False,
) -> None:
    """Replay a recorded run exactly and verify requests, state transitions and outcome."""
    store = _store(runs_dir)
    try:
        report = replay_run(store, run_id, support_replay_context(), policy_version=policy)
    except (RunNotFoundError, TraceStoreError) as exc:
        console.print(f"[red]{type(exc).__name__}: {exc}[/red]")
        raise typer.Exit(2) from exc
    saved_to: Path | None = None
    if save and report.replay is not None:
        store.save(report.replay)
        saved_to = store.root / report.replay.header.run_id
    _print_replay(report, saved_to)
    raise typer.Exit(_REPLAY_EXIT[report.verdict])


# Week 3 commands register themselves on ``app`` (inject, intervene, regress, investigate, bench).
from agenttrace import cli_diagnose as _cli_diagnose  # noqa: E402

__all__ = ["_cli_diagnose", "app"]

if __name__ == "__main__":  # pragma: no cover
    app()
