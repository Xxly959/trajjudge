"""Render the phase-1 report from existing local evidence without model calls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trajjudge.config import PROJECT_ROOT
from trajjudge.reporting import generate_report


def main(argv: list[str] | None = None) -> int:
    """Write a report; preserve incomplete verdicts and return a nonzero status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=PROJECT_ROOT / "outputs/grades/s6-offline.jsonl")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports/phase1.md")
    args = parser.parse_args(argv)
    result = generate_report(pilot_path=PROJECT_ROOT / "outputs/claw_eval/s5/pilot.json",
                             scores_path=args.scores, usage_path=PROJECT_ROOT / "outputs/usage/usage.jsonl",
                             pricing_path=PROJECT_ROOT / "configs/pricing.yaml", output_path=args.output)
    print(f"Report {'complete' if result.complete else 'INCOMPLETE'}: {args.output}")
    return 0 if result.complete else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Report stopped ({type(exc).__name__}); verify local evidence and accounting.", file=sys.stderr)
        raise SystemExit(1) from None
