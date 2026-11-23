"""``atrace`` command-line interface (Week 1: scenarios, run, show).

Exit codes for ``run``: 0 = oracle PASS, 1 = oracle FAIL, 2 = usage or execution error.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.table import Table

from agenttrace.env.support.scenario import list_scenario_ids, load_scenario
from agenttrace.policies.support_scripted import PolicyVersion
from agenttrace.runner import record_scenario
from agenttrace.trace.schema import Boundary, Event, Outcome, Trace
from agenttrace.trace.store import JsonlTraceStore, TraceStoreError

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
            state = f"committed ({len(event.state.delta)} changes)"
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
    record = record_scenario(scenario, policy_version=cast(PolicyVersion, policy))
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


if __name__ == "__main__":  # pragma: no cover
    app()
