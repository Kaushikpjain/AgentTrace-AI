"""Markdown investigation report (observable data and experiment summaries only)."""

from __future__ import annotations

from collections.abc import Sequence

from agenttrace.localize.types import Investigation
from agenttrace.trace.schema import Trace

_CAVEAT = (
    "`INTERVENTIONAL_REPAIR` means replacing this single step with its trusted reference was "
    "*sufficient to repair this run* while a same-type placebo reproduced the original failure. "
    "It is not proof of a unique cause; other repair sites are listed. `SUSPICION` and "
    "`REFERENCE_DEVIATION` are not causal evidence."
)


def render_markdown(trace: Trace, investigations: Sequence[Investigation]) -> str:
    header, footer = trace.header, trace.footer
    lines = [
        f"# Investigation: {header.run_id}",
        "",
        f"- Scenario `{header.scenario.id}` · agent `{header.agent.policy_id}:"
        f"{header.agent.policy_version}` · status `{footer.status.value}` · oracle "
        f"`{footer.outcome.outcome.value}`",
    ]
    for clause in footer.outcome.violated_clauses:
        lines.append(f"  - violated `{clause.clause_id}`: {clause.message}")
    lines += ["", f"> {_CAVEAT}", ""]
    for inv in investigations:
        lines += [
            f"## Method {inv.method}",
            "",
            f"Conclusion: **{inv.conclusion}** · symptom seq {inv.symptom_seq} · "
            f"replays used: {inv.replays_used}",
            "",
            "| rank | seq | step | label | score | flags | reference | intervention | placebo |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for rank, step in enumerate(inv.ranking, start=1):
            exp = step.experiment
            intervention = placebo = ""
            if exp is not None:
                itype = exp.intervention_type.value if exp.intervention_type else "-"
                result = (
                    exp.intervention_outcome.value
                    if exp.intervention_outcome
                    else exp.intervention_status.value
                )
                intervention = f"{itype} → {result}"
                placebo_outcome = exp.placebo_outcome.value if exp.placebo_outcome else "-"
                placebo = f"{placebo_outcome} ({'valid' if exp.placebo_valid else 'invalid'})"
            lines.append(
                f"| {rank} | {step.seq} | `{step.logical_key}` | {step.label.value} | "
                f"{step.score} | {', '.join(step.flags) or '-'} | {step.reference or '-'} | "
                f"{intervention or '-'} | {placebo or '-'} |"
            )
        for note in inv.notes:
            lines.append(f"\n_Note: {note}_")
        lines.append("")
    return "\n".join(lines)
