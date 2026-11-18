"""Validate deliveries, deduplicate by ID, and aggregate by logical order."""

import json
from pathlib import Path
import sys


FIELDS = {"event_id", "run_id", "attempt", "seq", "status"}
STATUSES = ("started", "timeout", "succeeded", "failed")


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def events_from(source):
    with source.open(encoding="utf-8", newline="\n") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line, object_pairs_hook=unique_object)
            if not isinstance(row, dict) or row.keys() != FIELDS:
                raise ValueError("expected the five event fields")
            if any(type(row[key]) is not str or not row[key] for key in ("event_id", "run_id")):
                raise ValueError("expected nonempty IDs")
            for key in ("event_id", "run_id"):
                row[key].encode("utf-8")
            if type(row["attempt"]) is not int or row["attempt"] < 1 or type(row["seq"]) is not int or row["seq"] < 0:
                raise ValueError("invalid attempt or sequence")
            if row["status"] not in STATUSES:
                raise ValueError("invalid status")
            yield row


def summarize(source):
    seen, positions, runs = {}, set(), {}
    for event in events_from(source):
        event_id, run_id = event["event_id"], event["run_id"]
        if event_id in seen:
            if seen[event_id] != event:
                raise ValueError("conflicting event ID")
            continue  # Identical delivery is already counted.
        order = (event["attempt"], event["seq"])
        position = (run_id, *order)
        if position in positions:
            raise ValueError("two event IDs at the same position")
        positions.add(position)
        seen[event_id] = event
        previous_order, previous_status, count = runs.get(run_id, ((0, -1), "", 0))
        if order > previous_order:
            previous_order, previous_status = order, event["status"]
        runs[run_id] = (previous_order, previous_status, count + 1)
    rows = [
        {"run_id": run_id, "attempt": order[0], "status": status, "unique_events": count}
        for run_id, (order, status, count) in sorted(runs.items())
    ]
    return {"runs": rows, "unique_events": len(seen)}


def main():
    sys.set_int_max_str_digits(0)
    try:
        source, target = map(Path, sys.argv[1:])
        document = summarize(source)
        payload = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        target.write_bytes(payload.encode("utf-8"))
    except (ValueError, OSError, RecursionError) as exc:
        print(f"event summary: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
