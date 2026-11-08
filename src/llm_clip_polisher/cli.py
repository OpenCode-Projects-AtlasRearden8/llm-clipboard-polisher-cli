"""Privacy-first clipboard polisher powered by a local OpenAI-compatible LLM.

Exit codes:
    0  success
    1  usage or input error
    2  config error
    3  endpoint unreachable or errored (fail-closed; clipboard is never touched)
    4  clipboard unavailable
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .clipboard import ClipboardError, read_clipboard, write_clipboard
from .config import (
    PolisherConfig,
    load_config,
    write_template_config,
)
from .history import append_history, default_history_path, make_entry
from .llm import EndpointError, normalize_source_text, polish_text
from .recipes import RECIPE_NAMES, build_messages, get_recipe

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_CONFIG = 2
EXIT_ENDPOINT = 3
EXIT_CLIPBOARD = 4

USAGE_NOTE = (
    "examples:\n"
    "  clipolish tighten            polish the clipboard text and copy it back\n"
    "  clipolish translate --to es  translate the clipboard text into Spanish\n"
    "  cat notes.txt | clipolish simplify --stdin\n"
    "  clipolish punctuate --in note.txt --print\n"
    f"recipes: {', '.join(RECIPE_NAMES)} (run one per command)\n"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipolish",
        description=(
            "Polish clipboard text with a local OpenAI-compatible model "
            "(Ollama included). One recipe per invocation. Text never leaves "
            "your machine except to the endpoint in your config."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE_NOTE,
    )
    parser.add_argument(
        "recipe",
        nargs="?",
        help=f"which rewrite to apply: {', '.join(RECIPE_NAMES)}",
    )
    parser.add_argument(
        "--to", metavar="LANG", help="target language (translate recipe only)"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read source text from stdin instead of the clipboard",
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        metavar="FILE",
        type=Path,
        help="read source text from a UTF-8 file instead of the clipboard",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        type=Path,
        metavar="FILE",
        help="config file with base_url and model",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="print the result instead of copying it to the clipboard",
    )
    parser.add_argument(
        "--log",
        dest="log",
        action="store_true",
        help="append a private local history entry (off by default)",
    )
    parser.add_argument(
        "--log-full",
        dest="log_full",
        action="store_true",
        help="with --log, store full text instead of 80-character previews",
    )
    parser.add_argument(
        "--template-config",
        action="store_true",
        help="write a starter config file to the default location and exit",
    )
    parser.add_argument(
        "--show-config", action="store_true", help="show the effective config and exit"
    )
    parser.add_argument(
        "--version", action="version", version=f"clipolish {__version__}"
    )
    return parser


def _load_config_step(
    explicit_path: Path | None, environ: dict[str, str]
) -> PolisherConfig:
    try:
        config = load_config(explicit_path, environ)
    except FileNotFoundError as exc:
        raise _Exit(EXIT_CONFIG, f"config file not found: {exc}")
    except ValueError as exc:
        raise _Exit(EXIT_CONFIG, f"config error: {exc}")
    return config


def _show_config(config: PolisherConfig) -> None:
    env_name = config.api_key_env_name()
    has_key = "set" if config.api_key else "not set (many local endpoints need none)"
    print(f"base_url          {config.base_url}")
    print(f"model             {config.model}")
    print(f"timeout_seconds   {config.timeout_seconds:g}")
    print(f"config file       {config.config_path or '(defaults)'}")
    print(f"api key source    {env_name}: {has_key}")


def _gather_source(
    args: argparse.Namespace,
    environ: dict[str, str],
    read_clipboard_fn=None,
) -> str:
    if sum([args.stdin, args.in_path is not None]) > 1:
        raise _Exit(EXIT_INPUT, "choose only one source: --stdin or --in FILE")
    if args.stdin:
        try:
            text = sys.stdin.read()
        except OSError as exc:
            raise _Exit(EXIT_INPUT, f"could not read stdin: {exc}")
    elif args.in_path is not None:
        try:
            text = args.in_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise _Exit(EXIT_INPUT, f"could not read {args.in_path}: {exc}")
    else:
        try:
            text = (read_clipboard_fn or read_clipboard)()
        except ClipboardError as exc:
            raise _Exit(EXIT_CLIPBOARD, str(exc))
    try:
        return normalize_source_text(text)
    except ValueError as exc:
        raise _Exit(EXIT_INPUT, str(exc))


def run(
    argv: list[str] | None = None,
    environ: dict[str, str] | None = None,
    read_clipboard_fn=None,
    write_clipboard_fn=None,
) -> int:
    environ = dict(os.environ) if environ is None else dict(environ)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.template_config:
        path = write_template_config(args.config_path, environ)
        print(f"wrote template config: {path}")
        return EXIT_OK

    if args.recipe is not None:
        try:
            recipe = get_recipe(args.recipe)
        except ValueError as exc:
            raise _Exit(EXIT_INPUT, str(exc) + "\nRun `clipolish --help` for examples.")
    elif not args.show_config:
        raise _Exit(
            EXIT_INPUT,
            "no recipe given; choose one of: "
            + ", ".join(RECIPE_NAMES)
            + "\nRun `clipolish --help` for examples.",
        )

    config = _load_config_step(args.config_path, environ)

    if args.show_config:
        _show_config(config)
        return EXIT_OK

    source = _gather_source(args, environ, read_clipboard_fn)
    try:
        messages = build_messages(recipe, args.to, source)
    except ValueError as exc:
        raise _Exit(EXIT_INPUT, str(exc))

    endpoint_label = f"{config.model} @ {config.base_url}"
    print(
        f"Sourcing {len(source)} characters ({recipe.name}"
        + (f" to {args.to}" if args.to else "")
        + f"), sending to {endpoint_label}...",
        file=sys.stderr,
    )
    try:
        result = polish_text(config, messages)
    except (EndpointError, ValueError) as exc:
        raise _Exit(
            EXIT_ENDPOINT,
            f"endpoint error (nothing was changed on your machine): {exc}",
        )

    if args.print_only:
        print(result)
    else:
        try:
            tool = (write_clipboard_fn or write_clipboard)(result)
        except ClipboardError as exc:
            print(result)
            raise _Exit(EXIT_CLIPBOARD, str(exc))
        print(f"polished text copied to the clipboard (via {tool}).", file=sys.stderr)
    if args.log:
        path = default_history_path(environ)
        entry = make_entry(
            recipe=recipe.name,
            target_language=args.to,
            model=config.model,
            base_url=config.base_url,
            source_text=source,
            result_text=result,
            full_text=args.log_full,
        )
        try:
            append_history(entry, path)
            print(
                f"logged to {path}"
                + (" (full text)" if args.log_full else " (previews only)"),
                file=sys.stderr,
            )
        except OSError as exc:
            raise _Exit(EXIT_CLIPBOARD, f"could not write history log: {exc}")
    return EXIT_OK


class _Exit(Exception):
    def __init__(self, code: int, message: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message


def main(argv: list[str] | None = None) -> int:
    try:
        code = run(argv)
    except _Exit as exit_exc:
        if exit_exc.code != EXIT_OK:
            print(f"clipolish: {exit_exc.message}", file=sys.stderr)
        return exit_exc.code
    except BrokenPipeError:
        return EXIT_OK
    except KeyboardInterrupt:
        print("clipolish: cancelled; nothing was changed.", file=sys.stderr)
        return EXIT_INPUT
    return code


def cli() -> None:
    sys.exit(main())


__all__ = ["build_parser", "cli", "main", "run"]
