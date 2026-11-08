"""Clipboard access via OS-native tools. Privacy-first: local subprocesses only."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass


class ClipboardError(Exception):
    """The clipboard could not be read or written on this machine."""


@dataclass(frozen=True)
class ClipboardTool:
    name: str
    read_cmd: Callable[[str], list[str]] | None
    write_cmd: Callable[[str], list[str]]


def _powershell_read(text: str) -> list[str]:
    return [
        "powershell",
        "-NoProfile",
        "-Command",
        "$OutputEncoding=[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard",
    ]


def _powershell_write(text: str) -> list[str]:
    command = (
        "$OutputEncoding=[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Set-Clipboard -Value ($input | Out-String)"
    )
    return ["powershell", "-NoProfile", "-Command", command]


_CANDIDATES: dict[str, tuple[ClipboardTool, ...]] = {
    "darwin": (
        ClipboardTool(
            name="pbpaste",
            read_cmd=lambda text: ["pbpaste"],
            write_cmd=lambda text: ["pbcopy"],
        ),
    ),
    "win32": (
        ClipboardTool(
            name="powershell", read_cmd=_powershell_read, write_cmd=_powershell_write
        ),
    ),
    "linux": (
        ClipboardTool(
            name="wl-copy",
            read_cmd=lambda text: ["wl-paste"],
            write_cmd=lambda text: ["wl-copy"],
        ),
        ClipboardTool(
            name="xclip",
            read_cmd=lambda text: ["xclip", "-selection", "clipboard", "-o"],
            write_cmd=lambda text: ["xclip", "-selection", "clipboard", "-i"],
        ),
        ClipboardTool(
            name="xsel",
            read_cmd=lambda text: ["xsel", "-b", "-o"],
            write_cmd=lambda text: ["xsel", "-b", "-i"],
        ),
    ),
}

FALLBACK_ORDER = ("win32", "linux", "darwin")


def _candidates(platform: str) -> tuple[ClipboardTool, ...]:
    if platform in _CANDIDATES:
        return _CANDIDATES[platform]
    collected: list[ClipboardTool] = []
    for look in FALLBACK_ORDER:
        if look in _CANDIDATES:
            candidate = _CANDIDATES[look]
            for tool in candidate:
                if tool not in collected:
                    collected.append(tool)
    return tuple(collected)


def candidate_names(platform: str = sys.platform) -> list[str]:
    return [tool.name for tool in _candidates(platform)]


def _run(
    cmd: list[str], input_text: str | None, timeout: float = 10.0
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=True,
    )


def _which_all(tool: ClipboardTool) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for cmd in [tool.read_cmd, tool.write_cmd]:
        if cmd is None:
            continue
        exe = cmd(text="")[0]
        if exe in seen:
            continue
        seen.add(exe)
        resolved = shutil.which(exe)
        if not resolved:
            continue
        names.append(resolved)
    return names


def write_clipboard(text: str, platform: str = sys.platform) -> str:
    attempts: list[str] = []
    for tool in _candidates(platform):
        if not _which_all(tool):
            attempts.append(f"{tool.name}: not installed")
            continue
        try:
            _run(tool.write_cmd(text), text)
            return tool.name
        except (OSError, subprocess.SubprocessError) as exc:
            attempts.append(f"{tool.name}: {exc.__class__.__name__}")
    raise ClipboardError(
        "could not copy to the clipboard: "
        + "; ".join(attempts)
        + ". Install a clipboard tool or use --print to see the text instead."
    )


def read_clipboard(platform: str = sys.platform) -> str:
    attempts: list[str] = []
    for tool in _candidates(platform):
        if tool.read_cmd is None or not _which_all(tool):
            attempts.append(f"{tool.name}: not installed")
            continue
        try:
            result = _run(tool.read_cmd(text=""), None)
        except (OSError, subprocess.SubprocessError) as exc:
            attempts.append(f"{tool.name}: {exc.__class__.__name__}")
            continue
        text = (result.stdout or "").strip()
        if text:
            return text
        attempts.append(f"{tool.name}: clipboard appears empty")
    raise ClipboardError(
        "could not read the clipboard on this machine (" + "; ".join(attempts) + "). "
        "Paste the text with --stdin or --in FILE instead."
    )
