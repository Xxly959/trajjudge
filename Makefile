VENV ?= .venvs/judge
PY ?= $(VENV)/bin/python
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
export UV_CACHE_DIR
export PYTHONDONTWRITEBYTECODE := 1
OPENJUDGE_ARGS ?=
SMOKE_ARGS ?=
SCORE_ARGS ?=

.PHONY: help install install-openjudge install-claw claw-preflight claw-pilot test secrets smoke smoke-openjudge score-trajectories phase1

help:
	@echo "install  create .venvs/judge and install trajjudge (editable) + dev deps"
	@echo "install-openjudge  install the read-only upstream editable (S3)"
	@echo "smoke-openjudge    run or replay the weather grader smoke (S3)"
	@echo "install-claw  install independent Claw host dependencies"
	@echo "claw-preflight  check the S5 sandbox without model calls"
	@echo "claw-pilot  run the fixed two-task S5 pilot once"
	@echo "score-trajectories  estimate S6 scoring; SCORE_ARGS=--run or --offline"
	@echo "test     run the offline test suite (all LLM calls are mocked)"
	@echo "secrets  fail if a provider-looking key is tracked by git"
	@echo "smoke    probe the DeepSeek endpoint (network, stage S2)"
	@echo "phase1   regenerate reports/phase1.md from cached grader output (S7)"

$(VENV)/pyvenv.cfg:
	uv venv --python 3.12 $(VENV)

install: $(VENV)/pyvenv.cfg
	uv pip install --python $(PY) -e ".[dev]"

install-openjudge: $(VENV)/pyvenv.cfg
	$(PY) scripts/install_openjudge.py

.venvs/claw/pyvenv.cfg:
	uv venv --python 3.12 .venvs/claw

install-claw: .venvs/claw/pyvenv.cfg
	.venvs/claw/bin/python scripts/install_claw.py

claw-preflight:
	.venvs/claw/bin/python scripts/run_claw_eval.py --preflight

claw-pilot:
	.venvs/claw/bin/python scripts/run_claw_eval.py --run

test:
	$(PY) -m pytest

secrets:
	$(PY) -m pytest tests/test_no_secrets.py -q

smoke:
	$(PY) scripts/smoke_llm.py $(SMOKE_ARGS)

smoke-openjudge:
	$(PY) scripts/smoke_openjudge.py $(OPENJUDGE_ARGS)

score-trajectories:
	$(PY) scripts/score_trajectories.py $(SCORE_ARGS)

phase1:
	$(PY) scripts/run_phase1.py

# These report targets read local artifacts only and never call a model.
.PHONY: phase2 phase3 phase4 rule-controls
phase2:
	$(PY) scripts/report_experiments.py p2
phase3:
	$(PY) scripts/report_experiments.py p3
phase4:
	$(PY) scripts/report_experiments.py p4
rule-controls:
	$(PY) scripts/experiment.py controls
	$(PY) scripts/report_experiments.py controls
