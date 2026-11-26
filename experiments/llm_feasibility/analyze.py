"""Summarise 2A.0 raw logs into results/summary.json (committed). No run is excluded."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 3)


def frac(flags: list[bool]) -> str:
    return f"{sum(flags)}/{len(flags)}"


def summarise(path: Path) -> dict[str, Any]:
    d = json.loads(path.read_text())
    runs = d["runs"] if "runs" in d else [d["checks"]["run"]]
    turns = [t for r in runs for t in r["turns"]]
    attempts = [a for t in turns for a in t["attempts"]]
    first = [t["attempts"][0] for t in turns]
    warm = [a["total_s"] for a in attempts if "total_s" in a and a.get("load_s", 0) < 1.0]
    mem = d["memory_samples"]
    swap = [m["swap_used_mb"] for m in mem if m["swap_used_mb"] is not None]
    levels = Counter(m["pressure_level"] for m in mem)
    agreements = [t for t in turns if "tool_agrees" in t]
    arg_checked = [t for t in agreements if t.get("args_agree") is not None]
    cold = d.get("warmup") or d.get("checks", {}).get("cold_load", {})
    executed = [r for r in runs if r.get("tool_calls") is not None]
    return {
        "file": path.name,
        "stage": d["stage"],
        "model": d["model"],
        "runs": len(runs),
        "runs_completed": sum(r["status"] == "COMPLETED" for r in runs),
        "runs_aborted": sum(r["status"] == "ABORTED" for r in runs),
        "aborts": dict(Counter(r.get("abort") for r in runs if r.get("abort"))),
        "task_success": f"{sum(r['outcome'] == 'PASS' for r in runs)}/{len(runs)}",
        "per_run": [
            {
                k: r.get(k)
                for k in (
                    "template",
                    "temperature",
                    "seed",
                    "status",
                    "outcome",
                    "violated",
                    "abort",
                    "tool_sequence",
                    "wall_s",
                )
            }
            for r in runs
        ],
        "decision_turns": len(turns),
        "first_attempt_valid": f"{sum(not a['error'] for a in first)}/{len(first)}",
        "valid_after_retry": f"{sum(t['decision'] is not None for t in turns)}/{len(turns)}",
        "retries": sum(len(t["attempts"]) - 1 for t in turns),
        "first_attempt_errors": dict(Counter(a["error"] for a in first if a["error"])),
        "tool_agreement_with_reference": frac([t["tool_agrees"] for t in agreements]),
        "arg_agreement_when_tool_agrees": frac([bool(t["args_agree"]) for t in arg_checked]),
        "executed_tool_calls": sum(r["tool_calls"] for r in executed),
        "calls_with_argument_error": sum(r["arg_error_calls"] for r in executed),
        "thinking_emitted": sum(bool(a.get("thinking_emitted")) for a in attempts),
        "timeouts": sum(a.get("error") == "TIMEOUT" for a in attempts),
        "cold_load_s": round(cold.get("load_s", 0), 3),
        "loaded_size_bytes": (cold.get("ps") or [{}])[0].get("size"),
        "warm_call_s": {
            "n": len(warm),
            "median": pct(warm, 0.5),
            "p90": pct(warm, 0.9),
            "max": max(warm, default=None),
        },
        "ttft_warm_s_median": pct(
            [
                a["load_s"] + a["prompt_eval_s"]
                for a in attempts
                if "prompt_eval_s" in a and a.get("load_s", 0) < 1.0
            ],
            0.5,
        ),
        "run_wall_s": {
            "median": pct([r["wall_s"] for r in runs], 0.5),
            "max": max(r["wall_s"] for r in runs),
        },
        "prompt_tokens": {
            "median": pct([a["prompt_tokens"] for a in attempts if a.get("prompt_tokens")], 0.5),
            "max": max(
                (a["prompt_tokens"] or 0 for a in attempts if "prompt_tokens" in a), default=None
            ),
        },
        "output_tokens": {
            "median": pct([a["output_tokens"] for a in attempts if a.get("output_tokens")], 0.5),
            "total": sum(a.get("output_tokens") or 0 for a in attempts),
        },
        "ollama_rss_mb_max": max(m["ollama_rss_mb_max"] for m in mem),
        "memory": {
            "samples": len(mem),
            "pressure_levels": {str(k): v for k, v in sorted(levels.items())},
            "critical_fraction": round(levels.get(4, 0) / len(mem), 3) if mem else None,
            "swap_before_mb": d["memory_before"]["swap_used_mb"],
            "swap_max_mb": max(swap) if swap else None,
            "swap_growth_mb": round(max(swap) - d["memory_before"]["swap_used_mb"], 1)
            if swap
            else None,
            "swap_after_unload_mb": d["memory_after_unload"]["swap_used_mb"],
            "watchdog_fired": d.get("memory_watchdog_fired", False),
        },
        "unloaded": d.get("loaded_after_unload") == [],
        "blocked_non_local": d.get("blocked_non_local"),
    }


def main() -> None:
    files = sorted((HERE / "raw").glob("stage*.json"))
    out = {
        "note": "Generated by analyze.py from all raw logs; no run excluded.",
        "results": [summarise(f) for f in files],
    }
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in out["results"]:
        print(json.dumps({k: v for k, v in r.items() if k != "per_run"}))


if __name__ == "__main__":
    main()
