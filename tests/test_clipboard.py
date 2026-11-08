import os
import stat

import pytest

from llm_clip_polisher import clipboard
from llm_clip_polisher.clipboard import ClipboardError, candidate_names


def stub_path_env(monkeypatch, bin_dir, known_names):
    monkeypatch.setenv(
        "PATH",
        str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
    )
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        (lambda name: str(bin_dir / name) if name in known_names else None),
    )


def test_macos_uses_native_tools():
    assert candidate_names("darwin") == ["pbpaste"]


def test_windows_uses_powershell():
    assert candidate_names("win32") == ["powershell"]


def test_linux_tools_prefers_wl_clipboard():
    names = candidate_names("linux")
    assert names == ["wl-copy", "xclip", "xsel"]


def test_unknown_platform_falls_back():
    names = candidate_names("plan9")
    assert names == ["powershell", "wl-copy", "xclip", "xsel", "pbpaste"]


def test_write_and_read_through_stub_tools(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    write_script = bin_dir / "wl-copy"
    write_script.write_text('#!/bin/sh\ncat > "$STUB_OUT"\n')

    read_script = bin_dir / "wl-paste"
    read_script.write_text('#!/bin/sh\ncat "$STUB_IN"\n')

    for script in (write_script, read_script):
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

    stored = tmp_path / "clipboard.txt"
    stored.write_text("Polished text", encoding="utf-8")

    monkeypatch.setenv("STUB_OUT", str(stored))
    monkeypatch.setenv("STUB_IN", str(stored))
    stub_path_env(monkeypatch, bin_dir, {"wl-copy", "wl-paste"})

    used = clipboard.write_clipboard("Polished text", platform="linux")
    assert used == "wl-copy"
    assert stored.read_text(encoding="utf-8") == "Polished text"
    assert clipboard.read_clipboard(platform="linux") == "Polished text"


def test_read_clipboard_fails_with_clear_message_when_no_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", (lambda name: None))
    with pytest.raises(ClipboardError) as err:
        clipboard.read_clipboard(platform="linux")
    assert "--stdin" in str(err.value)
    assert "--in FILE" in str(err.value)


def test_write_clipboard_fails_with_print_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", (lambda name: None))
    with pytest.raises(ClipboardError) as err:
        clipboard.write_clipboard("text", platform="linux")
    assert "--print" in str(err.value)


def test_read_clipboard_reports_empty_clipboard(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    read_script = bin_dir / "wl-paste"
    read_script.write_text("#!/bin/sh\nexit 0\n")
    read_script.chmod(read_script.stat().st_mode | stat.S_IEXEC)
    write_script = bin_dir / "wl-copy"
    write_script.write_text("#!/bin/sh\ncat > /dev/null\n")
    write_script.chmod(write_script.stat().st_mode | stat.S_IEXEC)
    stub_path_env(monkeypatch, bin_dir, {"wl-copy", "wl-paste"})
    with pytest.raises(ClipboardError, match="appears empty"):
        clipboard.read_clipboard(platform="linux")
