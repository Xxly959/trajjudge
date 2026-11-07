"""Guard paid execution and persistent stage budgets with all model work mocked."""
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from trajjudge.usage import Price


@pytest.fixture
def cli(tmp_path, monkeypatch, settings):
    spec = importlib.util.spec_from_file_location("experiment_cli", Path(__file__).parents[1] / "scripts/experiment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "root", tmp_path)
    monkeypatch.setattr(module, "frozen_traces", lambda: {"t": [{"role": "user", "content": "synthetic"}]})
    monkeypatch.setattr(module, "load_settings", lambda **kw: replace(settings, judge_model="deepseek-flash"))
    monkeypatch.setattr(module, "load_pricing", lambda p: {"deepseek-flash": Price(.3, 1.2)})
    return module


def test_default_plan_does_not_create_run_or_call_model(cli, monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["experiment", "p2"])
    assert cli.main() == 0
    assert not (tmp_path / "runs").exists()


def test_paid_mode_requires_positive_cap(cli, monkeypatch):
    monkeypatch.setattr("sys.argv", ["experiment", "p2", "--run"])
    with pytest.raises(SystemExit):
        cli.main()


def test_stage_budget_does_not_reset_when_resumed(cli, monkeypatch, tmp_path):
    ceilings = []
    def mocked_run(jobs, client, *args, **kwargs):
        ceilings.append(client.settings.budget_usd)
        return {"error": 0, "stopped_early": 0}
    monkeypatch.setattr(cli, "run_jobs", mocked_run)
    monkeypatch.setattr("sys.argv", ["experiment", "p2", "--run", "--cap-usd", "1"])
    cli.main()
    budget = tmp_path / "runs/p2-deepseek-flash/budget.json"
    before = budget.read_bytes()
    cli.main()
    assert ceilings == [1., 1.] and budget.read_bytes() == before
    monkeypatch.setattr("sys.argv", ["experiment", "p2", "--run", "--cap-usd", "2"])
    with pytest.raises(ValueError, match="original stage cap"):
        cli.main()


def test_single_attempt_policy_preserves_probe_cap(cli, monkeypatch):
    observed = []
    def mocked_run(jobs, client, *args, **kwargs):
        observed.append((client.max_attempts, client.settings.budget_usd, kwargs["workers"]))
        return {"error": 0, "stopped_early": 0}
    monkeypatch.setattr(cli, "run_jobs", mocked_run)
    monkeypatch.setattr("sys.argv", ["experiment", "probe", "--run", "--cap-usd", ".2",
                                   "--max-attempts", "1", "--workers", "1"])
    assert cli.main() == 0
    assert observed == [(1, .2, 1)]
