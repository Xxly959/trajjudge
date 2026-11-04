VENV ?= .venvs/judge
PY ?= $(VENV)/bin/python
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
export UV_CACHE_DIR

.PHONY: help install test secrets smoke phase1

help:
	@echo "install  create .venvs/judge and install trajjudge (editable) + dev deps"
	@echo "test     run the offline test suite (all LLM calls are mocked)"
	@echo "secrets  fail if a provider-looking key is tracked by git"
	@echo "smoke    probe the DeepSeek endpoint (network, stage S2)"
	@echo "phase1   regenerate reports/phase1.md from cached grader output (S7)"

$(VENV)/pyvenv.cfg:
	uv venv --python 3.12 $(VENV)

install: $(VENV)/pyvenv.cfg
	uv pip install --python $(PY) -e ".[dev]"

test:
	$(PY) -m pytest

secrets:
	$(PY) -m pytest tests/test_no_secrets.py -q

smoke:
	$(PY) scripts/smoke_llm.py

phase1:
	$(PY) scripts/run_phase1.py
