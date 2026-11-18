from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return runpy.run_path(str(ROOT / "scripts/run_original_api_pilot.py"))


def test_only_named_tools_with_exact_argument_shapes_are_admitted(api):
    parse = api["parse_tool"]
    assert parse(SimpleNamespace(call_id="valid", name="read_workspace", arguments="{}")) == ("read_workspace", {})
    for name, payload in (
        ("shell", '{"cmd":"pwd"}'),
        ("submit_solution", '{"source":"x","path":"elsewhere"}'),
        ("submit_solution", '{"source":null}'),
        ("read_workspace", "{"),
    ):
        with pytest.raises(ValueError):
            parse(SimpleNamespace(call_id="test", name=name, arguments=payload))


def test_api_wire_keeps_native_ids_and_json_strings(api):
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "provider-1", "type": "function",
          "function": {"name": "read_workspace", "arguments": {}}}]},
        {"role": "tool", "tool_call_id": "provider-1", "name": "read_workspace", "content": "fixture"},
    ]
    result = api["wire_messages"](messages)
    assert result[0]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert result[1] == {"role": "tool", "tool_call_id": "provider-1", "content": "fixture"}
    assert messages[0]["tool_calls"][0]["function"]["arguments"] == {}


def test_sandbox_exposes_only_disposable_case_directory(api, tmp_path):
    cmd = api["docker_command"]("pilot-test", tmp_path, ["-I", "solution.py", "input.jsonl", "result.json"])
    assert cmd[cmd.index("--network") + 1] == "none"
    assert "--read-only" in cmd
    assert cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert cmd.count("--mount") == 1
    assert cmd[cmd.index("--mount") + 1] == f"type=bind,source={tmp_path},target=/work"
    assert cmd[-5:] == ["python3", "-I", "solution.py", "input.jsonl", "result.json"]
