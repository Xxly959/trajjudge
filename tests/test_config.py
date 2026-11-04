"""Tests for configuration loading and dotenv parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from trajjudge.config import ConfigError, Settings, load_settings, read_dotenv


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_read_dotenv_parses_quotes_and_comments(tmp_path: Path) -> None:
    env = _write(
        tmp_path / ".env",
        "\n".join(
            [
                "# comment",
                "",
                "DEEPSEEK_API_KEY=abc123",
                "export DEEPSEEK_BASE_URL='https://api.deepseek.com'",
                "IGNORED_LINE",
            ]
        ),
    )

    values = read_dotenv(env)

    assert values == {
        "DEEPSEEK_API_KEY": "abc123",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    }


def test_read_dotenv_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_dotenv(tmp_path / "nope.env") == {}


def test_process_env_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = _write(tmp_path / ".env", "DEEPSEEK_API_KEY=from-file\n")
    config = _write(
        tmp_path / "deepseek.yaml",
        "base_url: https://api.deepseek.com\nmodels:\n  judge: j\n  agent: a\n",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")

    settings = load_settings(env_file=env, config_file=config)

    assert settings.api_key == "from-env"


def test_missing_api_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = _write(tmp_path / "deepseek.yaml", "models:\n  judge: j\n  agent: a\n")

    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        load_settings(env_file=tmp_path / "missing.env", config_file=config)


def test_missing_model_ids_raise_actionable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env = _write(tmp_path / ".env", "DEEPSEEK_API_KEY=k\n")
    config = _write(tmp_path / "deepseek.yaml", "models:\n  judge: null\n  agent: null\n")

    with pytest.raises(ConfigError, match="missing model id"):
        load_settings(env_file=env, config_file=config)


def test_require_models_false_allows_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env = _write(tmp_path / ".env", "DEEPSEEK_API_KEY=k\n")
    config = _write(tmp_path / "deepseek.yaml", "models:\n  judge: null\n  agent: null\n")

    settings = load_settings(env_file=env, config_file=config, require_models=False)

    assert settings.judge_model == ""


def test_model_for_rejects_unknown_role(settings: Settings) -> None:
    assert settings.model_for("judge") == "judge-test"
    assert settings.model_for("agent") == "agent-test"
    with pytest.raises(ConfigError):
        settings.model_for("grader")


def test_offline_settings_do_not_require_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = _write(tmp_path / "deepseek.yaml", "models:\n  judge: j\n  agent: a\n")
    result = load_settings(env_file=tmp_path / "missing.env", config_file=config, require_key=False)
    assert result.api_key == ""
