PY := .venvs/judge/bin/python
VENV := .venvs/judge

.PHONY: help install test secrets smoke phase1

help:
	@echo "install  create .venvs/judge and install trajjudge (editable) + dev deps"
	@echo "test     run the offline test suite (all LLM calls are mocked)"
	@echo "secrets  fail if a provider-looking key is tracked by git"
	@echo "smoke    probe the DeepSeek endpoint (network, stage S2)"
	@echo "phase1   regenerate reports/phase1.md from cached grader output (S7)"

install:
	uv venv --python 3.12 $(VENV)
	uv pip install --python $(PY) pip
	# pip (not `uv pip`) builds the editable wheel here: uv's source-build temp
	# handling fails with EEXIST on this machine. See notes/log.md, S1.
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest

secrets:
	$(PY) -m pytest tests/test_no_secrets.py -q

smoke:
	$(PY) scripts/smoke_llm.py

phase1:
	$(PY) scripts/run_phase1.py
