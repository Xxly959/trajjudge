"""Generate a synthetic mini-SWE-agent bundle for the offline importer."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def blob_id(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def write_bundle(root):
    root.mkdir()
    instance = "demo__project-1"
    patch = "diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-return 0\n+return 1\n"
    trajectory = {
        "instance_id": instance,
        "trajectory_format": "mini-swe-agent-1.1",
        "info": {"mini_version": "2.4.6", "exit_status": "Submitted", "submission": patch},
        "messages": [{"role": "user", "content": "Return one from the demo function."},
                     {"role": "assistant", "content": "Submitted the demo change."}],
        "extra_demo_field": "synthetic field value",
    }
    report = {instance: {
        "resolved": True, "infra_failure": False, "patch_is_None": False, "patch_exists": True,
        "patch_successfully_applied": True,
        "tests_status": {
            name: {"success": ["test_demo"] if name == "FAIL_TO_PASS" else [], "failure": []}
            for name in ("FAIL_TO_PASS", "PASS_TO_PASS", "FAIL_TO_FAIL", "PASS_TO_FAIL")
        },
    }}
    files = {
        f"trajs/{instance}.traj.json": json.dumps(trajectory).encode(),
        f"logs/{instance}/report.json": json.dumps(report).encode(),
        f"logs/{instance}/patch.diff": patch.encode(),
        f"logs/{instance}/test_output.txt.gz": gzip.compress(b"synthetic test log\n", mtime=0),
    }
    for path, data in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    bundle = {
        "repository": "demo/synthetic-artifacts", "revision": "1" * 40, "registry_revision": "2" * 40,
        "published_at": "2026-01-01T00:00:00Z", "agent_version": "2.4.6", "benchmark": "multilingual",
        "instances": [{"instance_id": instance, "registered_resolved": True}],
        "git_blobs": {path: blob_id(data) for path, data in files.items()},
    }
    (root / "bundle.json").write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="new directory for the example bundle")
    write_bundle(parser.parse_args().root)
