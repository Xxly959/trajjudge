"""Guard paid execution and persistent stage budgets with all model work mocked."""
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from trajjudge.annotation import save_labels
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


def test_p4_requires_exact_unlabeled_count_and_only_plans_owner_failures(cli, monkeypatch, tmp_path, capsys):
    candidates = [{"trace_id": tid, "task_id": tid, "passed": tid != "blank", "category": "test"}
                  for tid in ("fail", "pass", "blank")]
    meta = tmp_path / "outputs/p2/annotation_meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"chosen": candidates}))
    key = tmp_path / "outputs/annotation/key.json"
    key.parent.mkdir()
    key.write_text(json.dumps({"fail": "B1", "pass": "B2", "blank": "B3"}))
    labels = tmp_path / "annotation/labels.csv"
    labels.parent.mkdir()
    save_labels(labels, [{"blind_id": blind, "label": label, "reason": "fixture" if label else "", "round": "1"}
                         for blind, label in (("B1", "fail"), ("B2", "pass"), ("B3", ""))])
    before = labels.read_bytes()
    messages = [{"role": "tool", "content": "fixture"}, {"role": "assistant", "content": "done"}]
    monkeypatch.setattr(cli, "frozen_traces", lambda: {item["trace_id"]: messages for item in candidates})
    for args in ([], ["--expected-unlabeled", "2"]):
        monkeypatch.setattr("sys.argv", ["experiment", "p4", *args])
        with pytest.raises(ValueError, match="annotation|unlabeled"):
            cli.main()
    monkeypatch.setattr("sys.argv", ["experiment", "p4", "--expected-unlabeled", "1"])
    assert cli.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert (plan["traces"], plan["completions"]) == (1, 108)
    assert cli.human_fail_ids(expected_unlabeled=1) == {"fail"}
    assert labels.read_bytes() == before
    assert not (tmp_path / "runs").exists()
