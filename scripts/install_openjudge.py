"""Install upstream OpenJudge editable without writing build files into it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(root: Path) -> dict[str, str]:
    """Hash every upstream file except Git's internal state."""
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file() and ".git" not in path.relative_to(root).parts}


def main() -> int:
    """Install dependencies separately so package build directories never collide."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT.parent / "OpenJudge")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    cache = ROOT / ".cache" / "openjudge-build"
    cache.mkdir(parents=True, exist_ok=True)
    for name in ("metadata", "build"):
        (cache / name).mkdir(exist_ok=True)
    config = cache / "setuptools.cfg"
    config.write_text(f"[egg_info]\negg_base = {cache / 'metadata'}\n[build]\nbuild_base = {cache / 'build'}\n")
    before = fingerprint(upstream)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("DIST_EXTRA_CONFIG", None)
    common = ["uv", "pip", "install", "--python", sys.executable, "--cache-dir", str(ROOT / ".cache" / "uv")]
    dependencies = tomllib.loads((upstream / "pyproject.toml").read_text())["project"]["dependencies"]
    try:
        subprocess.run([*common, *dependencies], env=env, check=True)
        env["DIST_EXTRA_CONFIG"] = str(config)
        subprocess.run([*common, "--no-deps", "-e", str(upstream)], env=env, check=True)
    finally:
        after = fingerprint(upstream)
        changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
        (cache / "verification.json").write_text(json.dumps({"upstream_files": len(before), "changed_paths": changed}, indent=2) + "\n")
        if changed:
            raise RuntimeError("upstream files changed during installation; inspect local verification.json")
        print(f"Upstream file delta: 0 ({len(before)} files verified)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
