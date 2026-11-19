"""Configuration loading for the trajjudge research project.

Configuration is layered, lowest priority first:

1. defaults defined in this module,
2. ``configs/deepseek.yaml`` (endpoint, model ids, thinking switches, paths),
3. environment variables, read from ``.env`` first and the real process
   environment second (the process environment wins).

The API key is read from the environment only. It is never written to disk by
this module and never included in an exception message.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "configs" / "deepseek.yaml"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved runtime settings for every LLM call in this project."""

    api_key: str = field(repr=False)
    base_url: str
    judge_model: str
    agent_model: str
    judge_thinking: bool
    agent_thinking: bool
    cache_dir: Path
    usage_log: Path
    pricing_file: Path
    budget_usd: float = 3.0
    provider: str = "deepseek"
    thinking_style: str = "deepseek"

    def model_for(self, role: str) -> str:
        """Return the configured model id for ``role`` (``judge`` or ``agent``)."""
        if role == "judge":
            return self.judge_model
        if role == "agent":
            return self.agent_model
        raise ConfigError(f"unknown model role: {role!r}")


def read_dotenv(path: Path) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` dotenv file.

    Blank lines and ``#`` comments are ignored, surrounding quotes are stripped,
    and ``export`` prefixes are tolerated. Missing files yield an empty mapping.
    """
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"config file must contain a mapping: {path}")
    return loaded


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_settings(
    env_file: Path | None = None,
    config_file: Path | None = None,
    *,
    require_models: bool = True,
    require_key: bool = True,
) -> Settings:
    """Load settings from ``.env`` plus the YAML config.

    Args:
        env_file: Dotenv file to read. Defaults to ``<project>/.env``.
        config_file: YAML config to read. Defaults to ``configs/deepseek.yaml``.
        require_models: When true (the default), missing model ids raise
            :class:`ConfigError` instead of being returned as empty strings.
            Tests that only exercise unrelated behaviour pass ``False``.
        require_key: Set false for offline cache replay only.

    Raises:
        ConfigError: If the API key or a required model id is missing.
    """
    env_path = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
    config_path = Path(config_file) if config_file is not None else DEFAULT_CONFIG_FILE

    merged = read_dotenv(env_path)
    # The process environment outranks .env so CI can inject credentials.
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"):
        if os.environ.get(key):
            merged[key] = os.environ[key]

    raw = _load_yaml(config_path)
    models: Mapping[str, Any] = raw.get("models") or {}
    thinking: Mapping[str, Any] = raw.get("thinking") or {}
    paths: Mapping[str, Any] = raw.get("paths") or {}

    api_key = merged.get("DEEPSEEK_API_KEY", "").strip()
    if require_key and not api_key:
        raise ConfigError(
            f"DEEPSEEK_API_KEY is not set. Put it in {env_path} (git-ignored) "
            "or export it in the environment."
        )

    base_url = (merged.get("DEEPSEEK_BASE_URL") or raw.get("base_url") or "https://api.deepseek.com").rstrip("/")

    judge_model = str(models.get("judge") or "").strip()
    agent_model = str(models.get("agent") or "").strip()
    if require_models:
        missing = [name for name, value in (("judge", judge_model), ("agent", agent_model)) if not value]
        if missing:
            raise ConfigError(
                f"missing model id(s) {missing} in {config_path}. Run the S2 probe "
                "(`scripts/smoke_llm.py --list-models`) and copy the exact ids returned "
                "by the API — do not fill them from memory."
            )

    return Settings(
        api_key=api_key,
        base_url=base_url,
        judge_model=judge_model,
        agent_model=agent_model,
        judge_thinking=bool(thinking.get("judge", False)),
        agent_thinking=bool(thinking.get("agent", False)),
        cache_dir=_resolve_path(paths.get("cache_dir"), PROJECT_ROOT / ".cache" / "llm"),
        usage_log=_resolve_path(paths.get("usage_log"), PROJECT_ROOT / "outputs" / "usage" / "usage.jsonl"),
        pricing_file=PROJECT_ROOT / "configs" / "pricing.yaml",
    )


VALID_THINKING_STYLES = frozenset({"deepseek", "dashscope", "none"})
DEFAULT_PROVIDERS_FILE = PROJECT_ROOT / "configs" / "providers.yaml"


def load_provider_settings(
    provider: str,
    *,
    env_file: Path | None = None,
    providers_file: Path | None = None,
    require_models: bool = True,
    require_key: bool = True,
) -> Settings:
    """Load Settings for a named OpenAI-compatible provider from ``configs/providers.yaml`` (P1-4)."""
    env_path = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
    cfg_path = Path(providers_file) if providers_file is not None else DEFAULT_PROVIDERS_FILE
    raw = _load_yaml(cfg_path)
    providers = raw.get("providers") or {}
    if provider not in providers or not isinstance(providers[provider], Mapping):
        raise ConfigError(f"unknown provider {provider!r} in {cfg_path}; available: {sorted(providers)}")
    spec = providers[provider]
    api_key_env = str(spec.get("api_key_env") or "").strip()
    base_url_env = str(spec.get("base_url_env") or "").strip()
    if not api_key_env:
        raise ConfigError(f"provider {provider!r} missing api_key_env in {cfg_path}")

    merged = read_dotenv(env_path)
    for env_name in (api_key_env, base_url_env):
        if env_name and os.environ.get(env_name):
            merged[env_name] = os.environ[env_name]

    api_key = merged.get(api_key_env, "").strip()
    if require_key and not api_key:
        raise ConfigError(
            f"{api_key_env} is not set for provider {provider!r}. Put it in {env_path} "
            "(git-ignored) or export it in the environment."
        )
    base_url = (merged.get(base_url_env) if base_url_env else None) or str(spec.get("base_url") or "")
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise ConfigError(f"provider {provider!r} missing base_url in {cfg_path}")

    thinking_style = str(spec.get("thinking_style") or "none").strip().lower()
    if thinking_style not in VALID_THINKING_STYLES:
        raise ConfigError(f"invalid thinking_style {thinking_style!r} for provider {provider!r}")

    models: Mapping[str, Any] = spec.get("models") or {}
    judge_model = str(models.get("judge") or "").strip()
    agent_model = str(models.get("agent") or judge_model).strip()
    if require_models and not judge_model:
        raise ConfigError(f"provider {provider!r} missing models.judge in {cfg_path}")

    paths: Mapping[str, Any] = raw.get("paths") or {}
    return Settings(
        api_key=api_key,
        base_url=base_url,
        judge_model=judge_model,
        agent_model=agent_model,
        judge_thinking=bool((spec.get("thinking") or {}).get("judge", False)),
        agent_thinking=bool((spec.get("thinking") or {}).get("agent", False)),
        cache_dir=_resolve_path(paths.get("cache_dir"), PROJECT_ROOT / ".cache" / "llm"),
        usage_log=_resolve_path(paths.get("usage_log"), PROJECT_ROOT / "outputs" / "usage" / f"usage_{provider}.jsonl"),
        pricing_file=_resolve_path(paths.get("pricing_file"), PROJECT_ROOT / "configs" / "pricing_v3.yaml"),
        provider=provider,
        thinking_style=thinking_style,
    )
