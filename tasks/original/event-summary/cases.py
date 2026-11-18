"""Original black-box examples tied to the numbered task clauses."""

import json


def event(event_id, run_id="x", attempt=1, seq=0, status="succeeded"):
    return {"event_id": event_id, "run_id": run_id, "attempt": attempt, "seq": seq, "status": status}


def result(run_id, attempt, status, unique_events):
    return dict(run_id=run_id, attempt=attempt, status=status, unique_events=unique_events)


def case(name, clauses, rows, expected=None, *, invalid=False, prior=None):
    data = rows if isinstance(rows, bytes) else b"".join((json.dumps(row) + "\n").encode() for row in rows)
    return {"id": name, "clauses": clauses, "inputs": {"events.jsonl": data}, "args": ["events.jsonl"],
            "expected": expected, "exit": 2 if invalid else 0, "prior_output": prior}


SUBMISSION_ARGS = ["input.jsonl"]
SUBMITTED_RESULT = {"runs": [result("demo", 1, "succeeded", 1)], "unique_events": 1}
DUPLICATE = event("d")
ORDERED = [
    event("e1", seq=0, status="started"), event("e2", seq=4, status="timeout"),
    event("e3", attempt=2, seq=0, status="started"), event("e4", attempt=2, seq=1),
    event("e5", seq=9, status="failed"),
]
RETRIED = {"runs": [result("x", 2, "succeeded", 5)], "unique_events": 5}
CASES = [
    case("single-success", ["1", "4"], [event("e")], {"runs": [result("x", 1, "succeeded", 1)], "unique_events": 1}),
    case("empty-and-blank", ["1", "4"], b"\n  \n", {"runs": [], "unique_events": 0}),
    case("retry-and-late-arrival", ["3", "4"], ORDERED, RETRIED),
    case("permuted-events", ["3", "4"], [ORDERED[i] for i in (3, 2, 0, 4, 1)], RETRIED),
    case("duplicate-delivery", ["2", "4"], [DUPLICATE, dict(reversed(list(DUPLICATE.items())))],
         {"runs": [result("x", 1, "succeeded", 1)], "unique_events": 1}),
    case("unicode-and-run-order", ["3", "4"], [event("b", "雪", status="failed"), event("a", "alpha")],
         {"runs": [result("alpha", 1, "succeeded", 1), result("雪", 1, "failed", 1)], "unique_events": 2}),
    case("event-id-conflict", ["2", "5"], [event("e"), event("e", run_id="y")], invalid=True, prior=b"keep me\n"),
    case("sequence-conflict", ["2", "5"], [event("e"), event("f")], invalid=True),
    case("malformed-json", ["5"], b"{\n", invalid=True, prior=b"prior\n"),
    case("duplicate-json-key", ["5"],
         b'{"event_id":"d","event_id":"e","run_id":"x","attempt":1,"seq":0,"status":"failed"}\n', invalid=True),
    case("invalid-attempt-type", ["1", "5"], [event("e", attempt=True)], invalid=True),
    case("large-attempt", ["1", "3", "4"],
         b'{"event_id":"large","run_id":"x","attempt":1' + b"0" * 4300 + b',"seq":0,"status":"succeeded"}\n',
         {"runs": [result("x", 10**4300, "succeeded", 1)], "unique_events": 1}),
    case("invalid-utf8", ["5"], b"\xff\n", invalid=True),
    case("invalid-id-unicode", ["1", "5"], [event("\ud800")], invalid=True),
    {"id": "missing-input", "clauses": ["5"], "inputs": {}, "args": ["missing.jsonl"], "exit": 2},
]
