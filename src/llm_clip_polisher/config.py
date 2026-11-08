"""TOML config loading. Base URL, model, timeout; keys come from env only."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib as _toml_parser
except ModuleNotFoundError:
    import tomli as _toml_parser  # type: ignore[no-redef]

ENV_CONFIG_PATH = "LLM_CLIP_POLISHER_CONFIG"
ENV_API_KEY = "POLISHER_API_KEY"
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "llama3.1"
DEFAULT_TIMEOUT = 60.0
MAX_SOURCE_CHARS = 120_000
APP_DIR_NAME = "llm-clipboard-polisher"


@dataclass(frozen=True)
class PolisherConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT
    config_path: Path | None = None
    api_key_env: str | None = None
    api_key: str | None = None

    def api_key_env_name(self) -> str:
        return self.api_key_env or ENV_API_KEY

    def auth_header(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}


def config_search_paths(env: dict[str, str] | None = None) -> list[Path]:
    environ = env if env is not None else dict(os.environ)
    paths: list[Path] = []
    explicit = environ.get(ENV_CONFIG_PATH)
    if explicit:
        paths.append(Path(explicit))
    paths.append(default_config_path(environ))
    return paths


def default_config_path(environ: dict[str, str] | None = None) -> Path:
    environ = environ if environ is not None else dict(os.environ)
    if environ.get(ENV_CONFIG_PATH):
        return Path(environ[ENV_CONFIG_PATH])
    if sys.platform == "win32":
        appdata = environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / APP_DIR_NAME / "config.toml"
    xdg = environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_DIR_NAME / "config.toml"


def default_config_text() -> str:
    return (
        f'base_url = "{DEFAULT_BASE_URL}"\n'
        f'model = "{DEFAULT_MODEL}"\n'
        f"timeout_seconds = {DEFAULT_TIMEOUT:g}\n"
        "\n"
        "# If your endpoint requires a key, set the env var it reads, e.g.\n"
        f"# {ENV_API_KEY}\n"
        '# api_key_env = "' + ENV_API_KEY + '"\n'
    )


def _as_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    result = float(value)
    if result <= 0:
        raise ValueError(f"{name} must be greater than zero, got {result}")
    return result


def _as_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _as_optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string when set")
    return value


def _normalize_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"base_url must start with http:// or https://, got {value!r}")
    if url.endswith("/chat/completions"):
        url = url.rsplit("/chat/completions", 1)[0]
    return url


def load_config_from_dict(
    data: dict[str, Any],
    config_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> PolisherConfig:
    if not isinstance(data, dict):
        raise ValueError("config file must be TOML key/value tables")
    environ = environ if environ is not None else dict(os.environ)
    allowed = {"base_url", "model", "timeout_seconds", "api_key_env"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            "unknown config keys: "
            + ", ".join(sorted(unknown))
            + " (note: API keys deliberately live in environment variables, not this file)"
        )
    return PolisherConfig(
        base_url=_normalize_base_url(
            _as_text(data.get("base_url", DEFAULT_BASE_URL), "base_url")
        ),
        model=_as_text(data.get("model", DEFAULT_MODEL), "model"),
        timeout_seconds=_as_float(
            data.get("timeout_seconds", DEFAULT_TIMEOUT), "timeout_seconds"
        ),
        config_path=config_path,
        api_key_env=_as_optional_text(data.get("api_key_env"), "api_key_env"),
        api_key=None,
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return _toml_parser.load(handle)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValueError(f"could not parse config {path}: {exc}") from exc


def resolve_api_key(
    config: PolisherConfig, environ: dict[str, str] | None = None
) -> str | None:
    environ = environ if environ is not None else dict(os.environ)
    env_name = config.api_key_env_name()
    value = environ.get(env_name)
    if value is not None and value.strip() == "":
        raise ValueError(f"environment variable {env_name} is set but empty")
    return value or None


def load_config(
    explicit_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> PolisherConfig:
    environ = environ if environ is not None else dict(os.environ)
    paths = (
        [explicit_path] if explicit_path is not None else config_search_paths(environ)
    )
    last_missing: Path | None = None
    for path in paths:
        if path.is_file():
            data = _read_toml(path)
            config = load_config_from_dict(data, config_path=path, environ=environ)
            return PolisherConfig(
                base_url=config.base_url,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
                config_path=path,
                api_key_env=config.api_key_env,
                api_key=resolve_api_key(config, environ),
            )
        last_missing = path
    hint = (
        "; create a template with `clipolish --template-config`" if last_missing else ""
    )
    raise FileNotFoundError(
        f"no config file found; write one at {last_missing or default_config_path(environ)}"
        + hint
    )


def write_template_config(
    path: Path | None = None, environ: dict[str, str] | None = None
) -> Path:
    target = path if path is not None else default_config_path(environ)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(default_config_text(), encoding="utf-8")
    return target
