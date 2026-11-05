"""Exercise label CLI persistence and blind repeat identities without real labels."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trajjudge import annotation as kit


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("annotate_cli", Path(__file__).parents[1] / "scripts/annotate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ann = tmp_path / "annotation"
    (ann / "traces").mkdir(parents=True)
    monkeypatch.setattr(module, "ANN", ann)
    monkeypatch.setattr(module, "CSV_PATH", ann / "labels.csv")
    monkeypatch.setattr(module, "KEY", tmp_path / "key.json")
    module.KEY.write_text(json.dumps({"trace": "B1"}))
    (ann / "traces/B1.md").write_text("# Trace B1\n\noriginal evidence")
    kit.write_template(module.CSV_PATH, ["B1"])
    return module


def test_relabel_waits_and_uses_new_blind_id(cli) -> None:
    rows = kit.read_labels(cli.CSV_PATH)
    rows[0].update(label="fail", reason="synthetic fixture only", annotated_at=datetime.now(timezone.utc).isoformat())
    kit.save_labels(cli.CSV_PATH, rows)
    with pytest.raises(SystemExit, match="two days"):
        cli.relabel(10)
    rows[0]["annotated_at"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    kit.save_labels(cli.CSV_PATH, rows)
    cli.relabel(10)
    saved = kit.read_labels(cli.CSV_PATH)
    assert saved[0] == rows[0]
    assert saved[1]["blind_id"] != "B1" and saved[1]["label"] == saved[1]["reason"] == ""
    assert "B1" not in (cli.ANN / "traces" / f"{saved[1]['blind_id']}.md").read_text()
    assert json.loads(cli.KEY.with_name("round2_key.json").read_text())[saved[1]["blind_id"]] == "B1"


def test_check_detects_deleted_original_row(cli, capsys) -> None:
    kit.save_labels(cli.CSV_PATH, [])
    cli.check()
    assert "missing row for B1" in capsys.readouterr().out
