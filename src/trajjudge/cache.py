"""Content-addressed disk cache for LLM responses.

The cache key is a SHA-256 over the canonical JSON encoding of everything that
can change a response: model id, messages, generation parameters, tool schemas
and the thinking switch. A cache hit must never trigger a network request, so
the client checks this cache before it builds a transport call.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


def canonical_json(payload: Any) -> str:
    """Serialise ``payload`` deterministically (sorted keys, no stray spaces)."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def make_key(payload: Mapping[str, Any]) -> str:
    """Return the cache key for a request payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class DiskCache:
    """A flat directory of ``<sha256>.json`` files holding response payloads."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, key: str) -> Path:
        """Return the file path backing ``key``."""
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the cached payload, or ``None`` when absent or corrupt."""
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return loaded if isinstance(loaded, dict) else None

    def put(self, key: str, value: Mapping[str, Any]) -> Path:
        """Atomically persist ``value`` under ``key`` and return the file path."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(key)
        handle, tmp_name = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return path
