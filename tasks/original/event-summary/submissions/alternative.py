import json
import sys
from collections import Counter
from pathlib import Path


FIELDS = {"event_id", "run_id", "attempt", "seq", "status"}
STATUSES = {"started", "timeout", "succeeded", "failed"}


def object_from_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_constant(token):
    raise ValueError(f"invalid JSON constant {token!r}")


def read_event(line):
    record = json.loads(
        line, object_pairs_hook=object_from_pairs, parse_constant=reject_constant
    )
    if not isinstance(record, dict) or record.keys() != FIELDS:
        raise ValueError("expected an object with exactly the five event fields")

    event_id = record["event_id"]
    run_id = record["run_id"]
    attempt = record["attempt"]
    seq = record["seq"]
    status = record["status"]

    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a nonempty string")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a nonempty string")
    event_id.encode("utf-8")
    run_id.encode("utf-8")
    if type(attempt) is not int or attempt < 1:
        raise ValueError("attempt must be an integer at least 1")
    if type(seq) is not int or seq < 0:
        raise ValueError("seq must be a nonnegative integer")
    if not isinstance(status, str) or status not in STATUSES:
        raise ValueError("unrecognized status")

    return event_id, (run_id, attempt, seq, status)


def summarize(lines):
    events = {}
    occupied = set()
    counts = Counter()
    latest = {}

    for number, raw_line in enumerate(lines, 1):
        try:
            line = raw_line.decode("utf-8")
            if not line.strip():
                continue
            event_id, event = read_event(line)
            if event_id in events:
                if events[event_id] != event:
                    raise ValueError(f"conflicting records for event_id {event_id!r}")
                continue

            run_id, attempt, seq, status = event
            position = (run_id, attempt, seq)
            if position in occupied:
                raise ValueError(f"multiple events at {position!r}")

            occupied.add(position)
            events[event_id] = event
            counts[run_id] += 1
            order = (attempt, seq)
            if run_id not in latest or order > latest[run_id][0]:
                latest[run_id] = (order, status)
        except (ValueError, RecursionError) as error:
            raise ValueError(f"line {number}: {error}") from error

    runs = []
    for run_id in sorted(latest):
        (attempt, _), status = latest[run_id]
        runs.append(
            {
                "run_id": run_id,
                "attempt": attempt,
                "status": status,
                "unique_events": counts[run_id],
            }
        )
    return {"runs": runs, "unique_events": len(events)}


def main(args):
    if len(args) != 2:
        print("usage: python3 solution.py INPUT OUTPUT", file=sys.stderr)
        return 2

    # The format does not specify an upper bound on attempt or seq.
    sys.set_int_max_str_digits(0)
    input_path, output_path = map(Path, args)
    try:
        with input_path.open("rb") as source:
            summary = summarize(source)
        output = json.dumps(
            summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        output_path.write_bytes((output + "\n").encode("utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
