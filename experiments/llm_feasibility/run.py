# ruff: noqa: E501, UP041, SIM102, RUF100
"""2A.0 local LLM feasibility experiment (NOT production code; see docs/PHASE2_PLAN.md §2A.0).

An experimental policy implements the existing ``Policy`` protocol and runs through the unchanged
``run_episode`` / gateway / sandbox tools / oracle. Only dev templates T1-T4 are allowed.

Usage (one model at a time):
  uv run python experiments/llm_feasibility/run.py --stage A --model qwen3:1.7b-q4_K_M
  uv run python experiments/llm_feasibility/run.py --stage B --model ...
  uv run python experiments/llm_feasibility/run.py --stage C --model ...
Raw logs: experiments/llm_feasibility/raw/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agenttrace.env.support.scenario import TaskSpec, load_scenario
from agenttrace.env.support.tools import SUPPORT_TOOLS, SUPPORT_TOOLS_BY_NAME
from agenttrace.policies.reference import GoldSupportReference
from agenttrace.runner import episode_for
from agenttrace.runtime.loop import run_episode
from agenttrace.runtime.types import Decision, Observation

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
RAW = HERE / "raw"
BASE = CONFIG["runtime"]["endpoint"]
WATCHDOG_CRITICAL_S = 15
MEMORY_ABORT = threading.Event()
ARG_ERRORS = {"VALIDATION_ERROR", "NOT_FOUND", "INVALID_AMOUNT", "AMOUNT_EXCEEDS_ORDER_TOTAL"}

# ------------------------------------------------------------------ locality guard
_LOCAL = {"127.0.0.1", "::1", "localhost"}
_BLOCKED: list[str] = []
_orig_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    host = address[0] if isinstance(address, tuple) else str(address)
    if self.family in (socket.AF_INET, socket.AF_INET6) and host not in _LOCAL:
        _BLOCKED.append(str(host))
        raise ConnectionRefusedError(f"experiment locality guard: blocked {host}")
    return _orig_connect(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]

# ------------------------------------------------------------------ prompt and tool schemas
SYSTEM_PROMPT = """You are a customer-support agent. Resolve exactly one support ticket by calling tools.

Procedure:
1. Look up the customer (get_customer) and the order (get_order).
2. Find the applicable policy with search_policy, using a short query describing the issue \
(for example the issue type and the word "refund"). Use the rules of the returned policy.
3. Decide with the policy rules:
   - If the order status is not in the policy's refundable_statuses: close the ticket with \
resolution PENDING_DELIVERY.
   - The refund amount is the order total (if the ticket names a sku: that item's unit_price \
times quantity).
   - If the order's refunded_amount already covers that amount: close with ALREADY_REFUNDED.
   - If the order is final_sale and the policy does not allow final-sale refunds: close with DENIED.
   - If the amount exceeds the policy's refund_limit for the customer's tier: close with ESCALATED.
   - Otherwise call issue_refund for that amount with idempotency_key "refund:<ticket_id>", then \
close the ticket with REFUNDED.
   - If a lookup, the policy search or the refund fails unexpectedly: close with ESCALATED.
4. Call exactly one tool per reply. After close_ticket has succeeded, reply with one short \
sentence and no tool call."""


def _inline(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline $refs and simplify Optional/anyOf so both models see the same plain schema."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            if "anyOf" in node:
                kinds = [walk(x) for x in node["anyOf"] if x.get("type") != "null"]
                base = {k: v for k, v in node.items() if k not in ("anyOf", "default", "title")}
                if len(kinds) == 1:
                    return {**kinds[0], **base}
                return {**base, "type": "string", "description": "decimal amount, e.g. 80.00"}
            return {k: walk(v) for k, v in node.items() if k not in ("title", "$defs", "default")}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": _inline(t.args_model.model_json_schema()),
        },
    }
    for t in SUPPORT_TOOLS
]


# ------------------------------------------------------------------ Ollama client (stdlib)
class CallTimeout(Exception):
    pass


def _post(path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (TimeoutError, socket.timeout) as exc:
        raise CallTimeout(str(exc)) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise CallTimeout(str(exc)) from exc
        raise


def _get(path: str) -> dict[str, Any]:
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read())


def model_cfg(tag: str) -> dict[str, Any]:
    return next(m for m in CONFIG["models"] if m["tag"] == tag)


def chat(
    tag: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    seed: int,
    tools: bool = True,
    timeout: float | None = None,
) -> tuple[dict[str, Any], float]:
    body: dict[str, Any] = {
        "model": tag,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m",
        "options": {**CONFIG["options"], "temperature": temperature, "seed": seed},
    }
    if tools:
        body["tools"] = TOOLS
    if model_cfg(tag)["think"] is not None:
        body["think"] = model_cfg(tag)["think"]
    t0 = time.perf_counter()
    out = _post("/api/chat", body, timeout or CONFIG["call_timeout_s"])
    return out, time.perf_counter() - t0


def unload(tag: str) -> None:
    _post("/api/generate", {"model": tag, "keep_alive": 0}, 60)
    for _ in range(30):
        if not _get("/api/ps").get("models"):
            return
        time.sleep(1)


# ------------------------------------------------------------------ memory sampler
class MemorySampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.samples: list[dict[str, Any]] = []
        self._halt = threading.Event()
        self.critical_streak = 0

    def run(self) -> None:
        while not self._halt.is_set():
            sample = sample_memory()
            self.samples.append(sample)
            # Safety amendment (not a selection criterion): abort after sustained critical pressure.
            self.critical_streak = self.critical_streak + 1 if sample["pressure_level"] == 4 else 0
            if self.critical_streak >= WATCHDOG_CRITICAL_S:
                MEMORY_ABORT.set()
            self._halt.wait(1.0)

    def stop(self) -> None:
        self._halt.set()
        self.join(5)


def sample_memory() -> dict[str, Any]:
    level = subprocess.run(
        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True, text=True
    ).stdout.strip()
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    used = re.search(r"used = ([\d.]+)M", swap)
    ps = subprocess.run(["ps", "-axo", "rss=,command="], capture_output=True, text=True).stdout
    rss = [
        int(line.split(None, 1)[0])
        for line in ps.splitlines()
        if "ollama" in line.lower() and "run.py" not in line
    ]
    return {
        "t": time.time(),
        "pressure_level": int(level) if level.isdigit() else None,
        "swap_used_mb": float(used.group(1)) if used else None,
        "ollama_rss_mb_sum": round(sum(rss) / 1024, 1),
        "ollama_rss_mb_max": round(max(rss, default=0) / 1024, 1),
    }


# ------------------------------------------------------------------ parsing and validation
_TOOL_CALL_TEXT = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def parse(msg: dict[str, Any], closed: bool) -> tuple[Decision | None, str, dict[str, Any]]:
    """Return (decision, error, info). ``info`` never contains thinking text."""
    content = msg.get("content") or ""
    thinking = msg.get("thinking") or ""
    think_in_content = "<think>" in content
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    info = {
        "thinking_emitted": bool(thinking) or think_in_content,
        "thinking_chars": len(thinking),
        "parsed_from_content": False,
        "n_tool_calls": 0,
    }
    calls = msg.get("tool_calls") or []
    if not calls:
        found = _TOOL_CALL_TEXT.findall(content)
        if found:
            try:
                calls = [{"function": json.loads(f)} for f in found]
                info["parsed_from_content"] = True
            except json.JSONDecodeError:
                return None, "malformed tool-call JSON in content", info
    info["n_tool_calls"] = len(calls)
    if not calls:
        if closed:
            return Decision.final(summary=content[:200] or None), "", info
        return None, "no tool call while the ticket is still open", info
    if len(calls) > 1:
        return None, "more than one tool call in one reply", info
    fn = calls[0].get("function", {})
    name, args = fn.get("name"), fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return None, "arguments are not valid JSON", info
    if name not in SUPPORT_TOOLS_BY_NAME:
        return None, f"unknown tool {name!r}", info
    if not isinstance(args, dict):
        return None, "arguments are not an object", info
    try:
        SUPPORT_TOOLS_BY_NAME[name].args_model.model_validate(args)
    except ValidationError as exc:
        return None, f"invalid arguments: {exc.errors()[0]['msg']}", info
    return Decision(kind="tool_call", tool=name, args=args), "", info


def _num(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def agree(decision: Decision, reference: Decision) -> tuple[bool, bool | None]:
    """(tool agrees, args agree when the tool agrees)."""
    if decision.kind != reference.kind or decision.tool != reference.tool:
        return False, None
    if decision.kind == "final":
        return True, True
    a, r = dict(decision.args or {}), dict(reference.args or {})
    for skip in ("idempotency_key", "note"):
        a.pop(skip, None)
        r.pop(skip, None)
    if "amount" in a or "amount" in r:
        if _num(a.pop("amount", None)) != _num(r.pop("amount", None)):
            return True, False
    return True, a == r


# ------------------------------------------------------------------ experimental policy
class AbortRun(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _history_messages(task: TaskSpec, history: Sequence[Observation]) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Ticket: " + task.model_dump_json()},
    ]
    for obs in history:
        msgs.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": obs.tool, "arguments": obs.args}}],
            }
        )
        msgs.append(
            {"role": "tool", "tool_name": obs.tool, "content": obs.response.model_dump_json()}
        )
    return msgs


class ExperimentPolicy:
    policy_id = "experiment-llm"
    deterministic = False

    def __init__(self, tag: str, temperature: float, seed: int, run_id: str, log: Any) -> None:
        self.tag, self.temperature, self.seed, self.run_id, self.log = (
            tag,
            temperature,
            seed,
            run_id,
            log,
        )
        self.policy_version = f"{tag}@t{temperature}"
        self.source_hash = "experiment"
        self.reference = GoldSupportReference("v2")
        self.started = time.perf_counter()
        self.turns: list[dict[str, Any]] = []

    def decide(self, task: TaskSpec, history: Sequence[Observation]) -> Decision:
        if time.perf_counter() - self.started > CONFIG["run_wall_cap_s"]:
            raise AbortRun("RUN_WALL_CAP")
        if MEMORY_ABORT.is_set():
            raise AbortRun("MEMORY_WATCHDOG")
        closed = any(o.tool == "close_ticket" and o.response.status.value == "OK" for o in history)
        messages = _history_messages(task, history)
        est_tokens = sum(len(json.dumps(m)) for m in messages) / 3.5
        limit = CONFIG["options"]["num_ctx"] * CONFIG["context_guard_fraction"]
        if est_tokens > limit:
            raise AbortRun("CONTEXT_GUARD")
        turn: dict[str, Any] = {"run_id": self.run_id, "turn": len(self.turns), "attempts": []}
        decision: Decision | None = None
        for attempt in range(1 + CONFIG["max_repair_retries"]):
            try:
                out, wall = chat(self.tag, messages, temperature=self.temperature, seed=self.seed)
            except CallTimeout:
                turn["attempts"].append({"attempt": attempt, "error": "TIMEOUT"})
                self._log_turn(turn, None)
                raise AbortRun("MODEL_TIMEOUT") from None
            msg = out.get("message", {})
            decision, error, info = parse(msg, closed)
            prompt_tokens = out.get("prompt_eval_count")
            turn["attempts"].append(
                {
                    "attempt": attempt,
                    "error": error,
                    **info,
                    "wall_s": round(wall, 3),
                    "total_s": out.get("total_duration", 0) / 1e9,
                    "load_s": out.get("load_duration", 0) / 1e9,
                    "prompt_eval_s": out.get("prompt_eval_duration", 0) / 1e9,
                    "eval_s": out.get("eval_duration", 0) / 1e9,
                    "prompt_tokens": prompt_tokens,
                    "output_tokens": out.get("eval_count"),
                    "est_prompt_tokens": round(est_tokens),
                    "done_reason": out.get("done_reason"),
                    "content_chars": len(msg.get("content") or ""),
                }
            )
            if prompt_tokens and prompt_tokens >= limit:
                self._log_turn(turn, None)
                raise AbortRun("CONTEXT_GUARD")
            if decision is not None:
                break
            messages = [
                *messages,
                {"role": "assistant", "content": (msg.get("content") or "")[:2000]},
                {
                    "role": "user",
                    "content": f"Your previous reply was invalid: {error}. "
                    "Reply with exactly one valid tool call.",
                },
            ]
        self._log_turn(turn, decision)
        if decision is None:
            raise AbortRun("INVALID_AFTER_RETRY")
        ref = self.reference.reference_decision(task, history)
        tool_ok, args_ok = agree(decision, ref)
        turn.update(tool_agrees=tool_ok, args_agree=args_ok, reference_tool=ref.tool)
        return decision

    def _log_turn(self, turn: dict[str, Any], decision: Decision | None) -> None:
        turn["decision"] = None if decision is None else decision.model_dump(mode="json")
        self.turns.append(turn)


# ------------------------------------------------------------------ runs
def run_once(tag: str, template: str, temperature: float, seed: int, run_id: str) -> dict[str, Any]:
    scenario = load_scenario(template)
    if scenario.split != "dev":  # held-out templates are never used
        raise SystemExit(f"refusing non-dev scenario {template}")
    policy = ExperimentPolicy(tag, temperature, seed, run_id, None)
    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "run_id": run_id,
        "model": tag,
        "template": template,
        "temperature": temperature,
        "seed": seed,
    }
    try:
        record = run_episode(episode_for(scenario), policy)  # type: ignore[arg-type]
        result["status"] = record.footer.status.value
        result["outcome"] = record.footer.outcome.outcome.value
        result["violated"] = [c.clause_id for c in record.footer.outcome.violated_clauses]
        tools = [e for e in record.events if e.boundary.value == "TOOL"]
        codes = [((e.response or {}).get("error") or {}).get("code") for e in tools]
        result["tool_calls"] = len(tools)
        result["arg_error_calls"] = sum(1 for c in codes if c in ARG_ERRORS)
        result["error_codes"] = [c for c in codes if c]
        result["tool_sequence"] = [e.name for e in tools]
        result["abort"] = None
    except AbortRun as exc:
        result.update(
            status="ABORTED",
            outcome="FAIL",
            abort=exc.reason,
            tool_calls=None,
            arg_error_calls=None,
        )
    result["wall_s"] = round(time.perf_counter() - t0, 3)
    result["turns"] = policy.turns
    return result


def warmup(tag: str) -> dict[str, Any]:
    if _get("/api/ps").get("models"):
        raise SystemExit("another model is loaded; refusing to load a second one")
    out, wall = chat(
        tag,
        [{"role": "user", "content": "Reply with the word OK."}],
        temperature=0.0,
        seed=1,
        tools=False,
    )
    ps = _get("/api/ps").get("models", [])
    return {
        "wall_s": round(wall, 3),
        "load_s": out.get("load_duration", 0) / 1e9,
        "total_s": out.get("total_duration", 0) / 1e9,
        "thinking_emitted": bool(out.get("message", {}).get("thinking")),
        "ps": [
            {k: m.get(k) for k in ("name", "digest", "size", "size_vram", "context_length")}
            for m in ps
        ],
    }


def stage_a(tag: str) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks["cold_load"] = warmup(tag)
    checks["inference_ok"] = True
    # validator rejects bad calls (independent of the model)
    bad = [
        {
            "tool_calls": [
                {
                    "function": {
                        "name": "issue_refund",
                        "arguments": {"order_id": "O1", "amount": "abc"},
                    }
                }
            ]
        },
        {"tool_calls": [{"function": {"name": "delete_everything", "arguments": {}}}]},
        {
            "tool_calls": [
                {"function": {"name": "get_order", "arguments": {"order_id": "O1", "x": 1}}}
            ]
        },
        {"content": "I will help you."},
        {
            "tool_calls": [
                {"function": {"name": "get_order", "arguments": {"order_id": "O1"}}},
                {"function": {"name": "get_customer", "arguments": {"customer_id": "C1"}}},
            ]
        },
    ]
    checks["validator_rejects"] = [parse(m, closed=False)[1] for m in bad]
    checks["validator_all_rejected"] = all(checks["validator_rejects"])
    # one full multi-turn run (T1, temperature 0)
    run = run_once(tag, "T1", 0.0, CONFIG["seed_base"], "A-T1")
    checks["multi_turn_run"] = {
        k: run[k] for k in ("status", "outcome", "abort", "tool_sequence") if k in run
    }
    prompt_tokens = [a.get("prompt_tokens") for t in run["turns"] for a in t["attempts"]]
    checks["max_prompt_tokens"] = max((p for p in prompt_tokens if p), default=None)
    checks["first_call_valid"] = bool(run["turns"]) and not run["turns"][0]["attempts"][0]["error"]
    checks["thinking_emitted_any"] = any(
        a.get("thinking_emitted") for t in run["turns"] for a in t["attempts"]
    )
    # timeout path
    try:
        chat(
            tag,
            _history_messages(load_scenario("T1").task, []),
            temperature=0.0,
            seed=1,
            timeout=0.01,
        )
        checks["timeout_path"] = "no timeout raised"
    except CallTimeout:
        checks["timeout_path"] = "CallTimeout raised and classified"
    # locality guard
    try:
        socket.create_connection(("10.255.255.1", 9), timeout=1)
        checks["locality_guard"] = "NOT blocked"
    except ConnectionRefusedError as exc:
        checks["locality_guard"] = f"blocked ({exc})"
    checks["blocked_non_local_attempts"] = list(_BLOCKED)
    checks["run"] = run
    return checks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["A", "B", "C"], required=True)
    ap.add_argument("--model", required=True)
    args = ap.parse_args()
    model_cfg(args.model)
    RAW.mkdir(exist_ok=True)
    out_path = RAW / f"stage{args.stage}_{args.model.replace(':', '_')}_{int(time.time())}.json"
    sampler = MemorySampler()
    before = sample_memory()
    sampler.start()
    t0 = time.time()
    result: dict[str, Any] = {
        "stage": args.stage,
        "model": args.model,
        "started": t0,
        "memory_before": before,
        "config": CONFIG,
    }
    try:
        if args.stage == "A":
            result["checks"] = stage_a(args.model)
        else:
            result["warmup"] = warmup(args.model)
            runs = []
            if args.stage == "B":
                plan = [(t, 0.0, CONFIG["seed_base"]) for t in CONFIG["scenarios"]]
            else:
                plan = [
                    (t, temp, CONFIG["seed_base"] + rep)
                    for rep in range(CONFIG["repetitions"])
                    for temp in CONFIG["temperatures"]
                    for t in CONFIG["scenarios"]
                ]
            for i, (template, temp, seed) in enumerate(plan):
                if MEMORY_ABORT.is_set():
                    result["stopped"] = f"memory watchdog after {i} runs"
                    break
                if time.time() - t0 > CONFIG["total_wall_budget_s"]:
                    result["stopped"] = f"total wall budget reached after {i} runs"
                    break
                run = run_once(args.model, template, temp, seed, f"{args.stage}-{i:03d}")
                runs.append(run)
                print(
                    f"{i:03d} {template} t={temp} seed={seed} {run['status']} {run['outcome']} "
                    f"abort={run['abort']} {run['wall_s']}s",
                    flush=True,
                )
                out_path.write_text(json.dumps({**result, "runs": runs}, default=str))
            result["runs"] = runs
    finally:
        sampler.stop()
        result["memory_samples"] = sampler.samples
        result["memory_after_runs"] = sample_memory()
        try:
            unload(args.model)
        except Exception as exc:  # noqa: BLE001
            result["unload_error"] = repr(exc)
        result["loaded_after_unload"] = _get("/api/ps").get("models", [])
        result["memory_after_unload"] = sample_memory()
        result["finished"] = time.time()
        result["blocked_non_local"] = list(_BLOCKED)
        result["memory_watchdog_fired"] = MEMORY_ABORT.is_set()
        out_path.write_text(json.dumps(result, default=str))
        print(f"wrote {out_path}")
        if args.stage == "A":
            c = result["checks"]
            print(json.dumps({k: v for k, v in c.items() if k != "run"}, indent=1, default=str))
        lat = [
            a["total_s"]
            for r in result.get("runs", [])
            for t in r["turns"]
            for a in t["attempts"]
            if "total_s" in a
        ]
        if lat:
            print(f"calls={len(lat)} median_total_s={statistics.median(lat):.2f}")


if __name__ == "__main__":
    main()
