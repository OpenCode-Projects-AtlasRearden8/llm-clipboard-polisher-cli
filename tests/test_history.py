import json
import os
import pathlib
import stat
from datetime import UTC, datetime

from llm_clip_polisher.history import (
    HISTORY_FILE,
    PREVIEW_CHARS,
    append_history,
    default_history_path,
    make_entry,
)


def test_default_history_path_respects_env():
    environ = {"LLM_CLIP_POLISHER_DATA_DIR": "/tmp/custom-data"}
    assert default_history_path(environ) == pathlib.Path(
        "/tmp/custom-data/history.jsonl"
    )


def test_default_history_path_platforms():
    environ = {"XDG_DATA_HOME": "/data", "LLM_CLIP_POLISHER_DATA_DIR": ""}
    assert (
        default_history_path(environ)
        .as_posix()
        .endswith("llm-clipboard-polisher/history.jsonl")
    )


def test_preview_only_by_default():
    entry = make_entry(
        recipe="tighten",
        target_language=None,
        model="m",
        base_url="http://127/v1",
        source_text="a" * 200,
        result_text="b" * 50,
        now=datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert entry["source_preview"].startswith("a" * PREVIEW_CHARS)
    assert entry["source_preview"].endswith("…")
    assert entry["source_chars"] == 200
    assert entry["result_preview"] == "b" * 50
    assert entry["full_text_stored"] is False
    assert entry["timestamp"].startswith("2026-10-01T00:00:00")


def test_full_text_mode():
    entry = make_entry(
        recipe="simplify",
        target_language=None,
        model="m",
        base_url="http://127/v1",
        source_text="a" * 200,
        result_text="b" * 200,
        full_text=True,
    )
    assert entry["source_preview"] == "a" * 200
    assert entry["full_text_stored"] is True


def test_translate_entry_records_language():
    entry = make_entry(
        recipe="translate",
        target_language="es",
        model="m",
        base_url="http://127/v1",
        source_text="hi",
        result_text="hola",
    )
    assert entry["target_language"] == "es"
    assert entry["recipe"] == "translate"


def test_append_history_writes_jsonl_locked_down(tmp_path):
    path = tmp_path / "logs" / HISTORY_FILE
    entry = make_entry(
        recipe="punctuate",
        target_language=None,
        model="m",
        base_url="http://127/v1",
        source_text="hi",
        result_text="Hi.",
    )
    append_history(entry, path)
    append_history(entry, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["recipe"] == "punctuate"
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600
