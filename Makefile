# AgentTrace AI development commands. Requires uv (https://docs.astral.sh/uv/).
.PHONY: help install lint format typecheck test cov check smoke verify-bench bench-dev reproduce-dev audit demo clean

UV ?= uv
TMP := $(shell mktemp -d 2>/dev/null || echo /tmp/agenttrace)

help:
	@echo "install        create the isolated .venv from uv.lock"
	@echo "check          lint + format check + mypy + tests (what CI runs first)"
	@echo "cov            tests with coverage"
	@echo "smoke          CLI smoke test"
	@echo "verify-bench   benchmark files == deterministic regeneration"
	@echo "bench-dev      evaluate the dev split into evaluation/synth_v0-dev"
	@echo "reproduce-dev  run the dev evaluation twice and compare canonical outputs byte for byte"
	@echo "audit          pip-audit of the locked dependencies"
	@echo "demo           scripted three-minute terminal demonstration"

install:
	$(UV) sync --locked

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy

test:
	$(UV) run pytest

cov:
	HYPOTHESIS_PROFILE=ci $(UV) run pytest --cov=agenttrace --cov-report=term

check: lint
	$(UV) run ruff format --check .
	$(UV) run mypy
	$(UV) run pytest

smoke:
	$(UV) run atrace --help >/dev/null
	$(UV) run atrace scenarios >/dev/null
	$(UV) run atrace run T1 --no-save >/dev/null
	@echo "smoke OK"

verify-bench:
	$(UV) run atrace bench verify

bench-dev:
	$(UV) run atrace bench run --split dev

reproduce-dev:
	$(UV) run atrace bench run --split dev --out $(TMP)/a >/dev/null
	$(UV) run atrace bench run --split dev --out $(TMP)/b >/dev/null
	@for f in metrics.json config.json results.jsonl table.md failure_cases.md canonical_fingerprints.json; do \
	  cmp -s $(TMP)/a/$$f $(TMP)/b/$$f && echo "identical $$f" || { echo "DIFFERENT $$f"; exit 1; }; \
	done

audit:
	$(UV) export --format requirements-txt --frozen --no-emit-project > $(TMP)/requirements.txt
	uvx pip-audit -r $(TMP)/requirements.txt --require-hashes --disable-pip --progress-spinner off

demo:
	./scripts/demo.sh

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov runs
