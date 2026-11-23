#!/usr/bin/env bash
# AgentTrace AI: three-minute terminal demonstration (deterministic; no network, no LLM).
# Uses a temporary run store, so it never touches ./runs. Press Enter between steps,
# or set DEMO_NONINTERACTIVE=1 to run straight through.
set -euo pipefail

cd "$(dirname "$0")/.."
RUNS="$(mktemp -d)"
export ATRACE_RUNS_DIR="$RUNS" COLUMNS="${COLUMNS:-120}"
at() { uv run --quiet atrace "$@"; }
step() {
  printf '\n\033[1;36m== %s\033[0m\n' "$1"
  if [ -z "${DEMO_NONINTERACTIVE:-}" ]; then read -r -p "(press Enter) " _; fi
}
last_run() { ls -t "$RUNS" | grep '^run-' | head -1; }

step "1. A clean agent run: support ticket T1 (damaged item, refund within limit)"
at run T1 || true

step "2. Fault injection: benchmark instance T1-D1+F4 (a harmless decoy read + wrong policy document)"
at inject T1-D1+F4 || true
FAILED="$(last_run)"

step "3. The failed execution trace, reloaded and integrity-checked"
at show "$FAILED"

step "4. Strict replay: re-execute the recording and verify every state transition and the outcome"
at replay "$FAILED"

step "5. Suspicious-step ranking: B1, B3, B4 (B4 is fooled by the decoy) and the counterfactual CF"
at investigate "$FAILED" --top 3

step "6 + 7. Controlled counterfactual on the retrieval step (seq 11), with a same-type placebo"
at intervene "$FAILED" --seq 11 --type execution

step "8. Diagnostic evidence: the placebo-controlled repair is the strongest label we give"
echo "INTERVENTIONAL_REPAIR at seq 11 = replacing that single step with its trusted reference was"
echo "sufficient to repair this run while the placebo reproduced the failure. It is not proof of"
echo "a unique cause. The decoy deviated from its reference but its intervention did not repair."

step "Bonus: regression. A lost acknowledgement makes agent v1 refund twice; v2 fixes it"
at inject T1-F5 || true
at regress "$(last_run)" --policy v2 || true

printf '\n\033[1;32mDemo complete.\033[0m Run store: %s\n' "$RUNS"
