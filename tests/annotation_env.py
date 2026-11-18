"""Shared synthetic annotation environment for the Phase 2 tests. Never contains real labels."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trajjudge import annotation as kit

FIXTURES = Path(__file__).parent / "fixtures" / "claw_s5"
SCRIPTS = Path(__file__).parents[1] / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_item(tmp_path: Path, task_id: str, prefix: str) -> dict:
    """A frozen-set item backed by a real trace fixture, with honest hashes."""
    directory = tmp_path / "evidence"
    directory.mkdir(exist_ok=True)
    trace = directory / f"{task_id}_{prefix}.jsonl"
    sidecar = directory / f"{task_id}_{prefix}.sidecar.jsonl"
    shutil.copyfile(FIXTURES / "contact.jsonl", trace)
    shutil.copyfile(FIXTURES / "contact.sidecar.jsonl", sidecar)
    return {"trace_id": f"{prefix}-0000-0000-0000-000000000000", "trace": str(trace), "sidecar": str(sidecar),
            "criteria": "be correct and safe",
            "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
            "sidecar_sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest()}


def build_env(tmp_path: Path, monkeypatch, *, count: int = 10, labeled: int = 8) -> dict:
    """``count`` traces in ``count // 2`` scenarios (translation twins); the tail stays blank."""
    cli = load_script("annotate")
    ann = tmp_path / "annotation"
    (ann / "traces").mkdir(parents=True)
    monkeypatch.setattr(cli, "ANN", ann)
    monkeypatch.setattr(cli, "CSV_PATH", ann / "labels.csv")
    monkeypatch.setattr(cli, "KEY", tmp_path / "key.json")
    tasks = [f"T{i:03d}_{'zh' if i % 2 else 'en'}_demo" for i in range(count)]
    items = [frozen_item(tmp_path, task, f"{i:08x}") for i, task in enumerate(tasks)]
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps(items))
    monkeypatch.setattr(cli, "FROZEN_SET", frozen)
    mapping = kit.blind_ids([i["trace_id"] for i in items], seed=11)
    cli.KEY.write_text(json.dumps(mapping))
    for item in items:
        blind = mapping[item["trace_id"]]
        (ann / "traces" / f"{blind}.md").write_text(cli._render_frozen(item, blind), encoding="utf-8")
    kit.write_template(cli.CSV_PATH, sorted(mapping.values()))
    rows = kit.read_labels(cli.CSV_PATH)
    stamp = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(timespec="seconds")
    for index, row in enumerate(rows):
        if index < labeled:
            row.update(label="pass" if index % 2 else "fail",
                       reason=f"synthetic fixture reason {index} citing tool output", annotated_at=stamp)
    kit.save_labels(cli.CSV_PATH, rows)
    scenarios = tmp_path / "scenario_map.csv"
    scenarios.write_text("task_id,scenario_id\n" + "".join(
        f"{task},demo{index // 2}\n" for index, task in enumerate(tasks)))
    return {"cli": cli, "ann": ann, "items": items, "mapping": mapping, "rows": rows,
            "frozen": frozen, "scenarios": scenarios, "tmp": tmp_path}


def resolve_blanks(env: dict) -> None:
    """Retire the blank rows the way the owner would, so round 1 is complete."""
    for row in kit.read_labels(env["cli"].CSV_PATH):
        if not row["label"]:
            env["cli"].exclude(row["blind_id"], "fixture: cannot decide from this evidence", "1")