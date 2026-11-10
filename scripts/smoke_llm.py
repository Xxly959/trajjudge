"""Run the bounded S2 probe through the shared client; never expose secrets."""

from __future__ import annotations

import sys

from trajjudge.config import ConfigError
from trajjudge.llm import LLMError
from trajjudge.smoke import main

if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (ConfigError, LLMError, OSError, ValueError) as exc:
        print(f"Smoke probe stopped ({type(exc).__name__}). See safe usage records for status.", file=sys.stderr)
        raise SystemExit(1) from None
