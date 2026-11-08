"""Opt-in private local history log (JSONL), previews by default, full text only if asked."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ENV_DATA_DIR = "LLM_CLIP_POLISHER_DATA_DIR"
APP_DIR_NAME = "llm-clipboard-polisher"
HISTORY_FILE = "history.jsonl"
PREVIEW_CHARS = 80


def default_history_path(environ: dict[str, str] | None = None) -> Path:
    environ = environ if environ is not None else dict(os.environ)
    if environ.get(ENV_DATA_DIR):
        base = Path(environ[ENV_DATA_DIR])
    elif sys.platform == "win32":
        base = (
            Path(environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
            / APP_DIR_NAME
        )
    else:
        xdg = environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_DIR_NAME
    return base / HISTORY_FILE


def make_entry(
    recipe: str,
    target_language: str | None,
    model: str,
    base_url: str,
    source_text: str,
    result_text: str,
    full_text: bool = False,
    now: datetime | None = None,
) -> dict:
    timestamp = now or datetime.now(UTC)
    entry = {
        "timestamp": timestamp.astimezone(UTC).isoformat(timespec="seconds"),
        "recipe": recipe,
        "target_language": target_language,
        "model": model,
        "base_url": base_url,
        "source_chars": len(source_text),
        "result_chars": len(result_text),
        "source_preview": _preview(source_text, full_text),
        "result_preview": _preview(result_text, full_text),
        "full_text_stored": full_text,
    }
    return entry


def _preview(text: str, full_text: bool) -> str | None:
    if full_text:
        return text
    if len(text) <= PREVIEW_CHARS:
        return text
    return text[:PREVIEW_CHARS] + "…"


def append_history(
    entry: dict,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
