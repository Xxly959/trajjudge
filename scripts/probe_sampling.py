#!/usr/bin/env python
"""Compatibility entry point for the frozen, budget-capped experiment driver."""
import sys
from experiment import main

if __name__ == "__main__":
    sys.argv.insert(1, "probe")
    raise SystemExit(main())
