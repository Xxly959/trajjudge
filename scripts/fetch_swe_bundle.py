#!/usr/bin/env python3
"""Acquire the plan's pinned public SWE-bench sample as local evidence."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from build_cross_source import blob_id, evidence_paths, json_document
from build_dataset import json_text


SUBMISSION = "20260902_mini-v2.4.6_gemini-3-5-flash"
ARTIFACTS = f"SWE-bench/{SUBMISSION}"
REVISION = "8dcca98587e7f698753903e3b1747eb5dc013cb1"
REGISTRY = "SWE-bench/experiments"
REGISTRY_REVISION = "40f164d5b8f1d249bf95a6df8b74b577fd8e519d"
ENTRY = f"evaluation/multilingual/{SUBMISSION}"


def get(url):
    request = Request(url, headers={"User-Agent": "TrajJudge-P1-evidence"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                return response.read()
        except (URLError, TimeoutError) as exc:
            if attempt == 2:
                raise OSError(f"{url}: {exc}") from None


def tree(repo, revision):
    url = f"https://api.github.com/repos/{repo}/git/trees/{revision}?recursive=1"
    document = json_document(get(url))
    if document["sha"] != revision or document["truncated"]:
        raise ValueError(f"unexpected or truncated tree for {repo}")
    return {entry["path"]: entry["sha"] for entry in document["tree"] if entry["type"] == "blob"}


def fetch_blob(repo, revision, path, expected):
    url = f"https://raw.githubusercontent.com/{repo}/{revision}/{quote(path)}"
    data = get(url)
    if blob_id(data) != expected:
        raise ValueError(f"Git blob mismatch for {url}")
    return data


def write_blob(root, path, data):
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def acquire(root):
    with ThreadPoolExecutor(max_workers=12) as pool:
        artifact_tree = pool.submit(tree, ARTIFACTS, REVISION)
        registry_tree = pool.submit(tree, REGISTRY, REGISTRY_REVISION)
        commit_url = f"https://api.github.com/repos/{ARTIFACTS}/commits/{REVISION}"
        commit = json_document(get(commit_url))
        if commit["sha"] != REVISION:
            raise ValueError("unexpected artifact revision")
        artifacts, registry = artifact_tree.result(), registry_tree.result()
        registry_files = ("metadata.yaml", "per_instance_details.json", "results/results.json")
        registration = {
            path: fetch_blob(REGISTRY, REGISTRY_REVISION, f"{ENTRY}/{path}", registry[f"{ENTRY}/{path}"])
            for path in registry_files
        }
        if REVISION.encode() not in registration["metadata.yaml"] or ARTIFACTS.encode() not in registration["metadata.yaml"]:
            raise ValueError("registry metadata does not point to the pinned artifact repository and revision")
        details = json_document(registration["per_instance_details.json"])
        results = json_document(registration["results/results.json"])
        resolved = set(results["resolved"])
        trajectories = {p.removeprefix("trajs/").removesuffix(".traj.json")
                        for p in artifacts if p.startswith("trajs/") and p.endswith(".traj.json")}
        log_ids = {p.split("/")[1] for p in artifacts if p.startswith("logs/")}
        complete_logs = {
            instance for instance in log_ids
            if all(path in artifacts for role, path in evidence_paths(instance).items() if role != "trajectory")
        }
        eligible = trajectories & complete_logs
        by_repo = defaultdict(lambda: {True: [], False: []})
        for instance in sorted(eligible):
            outcome = details[instance]["resolved"]
            if type(outcome) is not bool or outcome != (instance in resolved):
                raise ValueError(f"registry outcome mismatch for {instance}")
            by_repo[instance.rsplit("-", 1)[0]][outcome].append(instance)
        repos = [name for name in sorted(by_repo) if all(by_repo[name].values())][:4]
        if len(repos) != 4:
            raise ValueError("fewer than four repositories with paired pass/fail evidence")
        selected = sorted(ids[0] for name in repos for ids in by_repo[name].values())
        paths = {path: artifacts[path] for instance in selected for path in evidence_paths(instance).values()}
        downloads = {path: pool.submit(fetch_blob, ARTIFACTS, REVISION, path, sha) for path, sha in paths.items()}
        for path, future in downloads.items():
            write_blob(root, path, future.result())
    for path, data in registration.items():
        write_blob(root, f"registration/{path}", data)
    bundle = {
        "repository": ARTIFACTS, "revision": REVISION, "registry_revision": REGISTRY_REVISION,
        "agent_version": "2.4.6", "benchmark": "multilingual", "published_at": commit["commit"]["committer"]["date"],
        "git_blobs": paths, "instances": [{"instance_id": i, "registered_resolved": i in resolved} for i in selected],
        "inventory": {"trajectory_count": len(trajectories), "complete_logs_count": len(complete_logs),
                      "paired_count": len(eligible), "without_complete_logs": sorted(trajectories - complete_logs),
                      "without_matching_trajectory": sorted(complete_logs - trajectories)},
    }
    (root / "bundle.json").write_text(json_text(bundle) + "\n")
    print(f"Acquired {len(selected)} instances and verified {len(paths)} artifact Git blobs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="new directory for the local evidence bundle")
    root = parser.parse_args().root
    try:
        root.mkdir(parents=True)
        acquire(root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"acquisition failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
