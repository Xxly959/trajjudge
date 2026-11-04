"""Run the P2 Claw-Eval batch with the audited S5 bindings (read-only upstream)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "src"), str(root.parent / "claw-eval" / "src")]

from trajjudge.claw_batch import main
from trajjudge.claw_bridge import S5Stop

if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except S5Stop as exc:
        print(f"P2 stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
