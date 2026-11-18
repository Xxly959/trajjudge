import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "samples/swe_import_demo.py"
SCRIPT = ROOT / "scripts/build_cross_source.py"
TASK = "demo__project-1"


def invoke(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)


def export(tmp_path, bundle, *args):
    output = tmp_path / "export"
    result = invoke(SCRIPT, "--bundle", bundle, "--output", output, *args)
    assert (output / "CURRENT").exists(), result.stderr
    gen = output / "snapshots" / (output / "CURRENT").read_text().strip()
    return (result, [json.loads(line) for line in (gen / "trajectories.jsonl").read_text().splitlines()],
            json.loads((gen / "quality.json").read_text()))


def test_cross_source_keeps_same_raw_task_id_separate(tmp_path):
    bundle = tmp_path / "swe"
    assert invoke(DEMO, bundle).returncode == 0
    claw = tmp_path / "claw"
    demo = runpy.run_path(str(ROOT / "samples/dataset_demo.py"))
    demo["write_demo"](claw, TASK)
    assert invoke(ROOT / "scripts/build_dataset.py", "--root", claw).returncode == 0
    pointer = claw / "outputs/dataset/CURRENT"
    before = pointer.read_bytes()
    result, rows, quality = export(tmp_path, bundle, "--claw-root", claw)
    assert result.returncode == 0, result.stderr
    assert pointer.read_bytes() == before
    same_raw = [r for r in rows if r["task"]["native_id"] == TASK]
    assert len(same_raw) == 3
    assert len({r["task"]["id"] for r in same_raw}) == 2
    assert len({r["trial"]["id"] for r in same_raw}) == 3
    assert quality["sources"]["claw-eval"]["trials"] == 3
    assert quality["sources"]["swe-bench"]["trials"] == 1
    swe = next(r for r in rows if r["task"]["namespace"] == "swe-bench")
    assert swe["outcome"]["status"] == "pass"
    assert swe["outcome"]["reverified"] is False
    assert set(swe["trial"]["evidence"]) == {"trajectory", "report", "patch", "test_log"}
    assert "extra_demo_field" in quality["sources"]["swe-bench"]["unknown_fields"]["trajectory"]
    assert "synthetic field value" not in json.dumps(swe)


@pytest.mark.parametrize(("damage", "reason"), [
    ("missing", "missing_evidence"),
    ("instance", "instance_mismatch"),
    ("result", "registry_result_mismatch"),
    ("patch", "submission_mismatch"),
    ("tamper", "git_blob_mismatch"),
    ("overflow", "invalid_evidence"),
])
def test_bad_external_evidence_is_excluded_with_reason(tmp_path, damage, reason):
    bundle = tmp_path / "swe"
    assert invoke(DEMO, bundle).returncode == 0
    demo = runpy.run_path(str(DEMO))
    descriptor_path = bundle / "bundle.json"
    descriptor = json.loads(descriptor_path.read_text())
    path = f"logs/{TASK}/report.json"
    if damage == "missing":
        (bundle / f"logs/{TASK}/test_output.txt.gz").unlink()
    elif damage == "result":
        descriptor["instances"][0]["registered_resolved"] = False
    else:
        if damage == "instance":
            doc = json.loads((bundle / path).read_text())
            (bundle / path).write_text(json.dumps({"demo__project-2": doc[TASK]}))
        elif damage == "patch":
            path = f"logs/{TASK}/patch.diff"
            (bundle / path).write_text("another submitted patch")
        elif damage == "overflow":
            path = f"trajs/{TASK}.traj.json"
            text = (bundle / path).read_text().replace('"Submitted the demo change."', '1e999')
            (bundle / path).write_text(text)
        else:
            (bundle / path).write_text("{}")
        if damage != "tamper":
            descriptor["git_blobs"][path] = demo["blob_id"]((bundle / path).read_bytes())
    descriptor_path.write_text(json.dumps(descriptor))
    result, rows, quality = export(tmp_path, bundle)
    assert result.returncode == 1
    assert rows == []
    assert quality["sources"]["swe-bench"]["excluded"][0]["reason"] == reason
