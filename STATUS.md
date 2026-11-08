# STATUS — llm-clipboard-polisher (clipolish)

Last updated: 2026-11-08 · Owner: Asdale Dynamics, LLC

## What was built

`clipolish` — a privacy-first Python CLI that polishes clipboard text with a locally
configured, OpenAI-compatible endpoint (Ollama included). One rewrite recipe per
invocation: `tighten`, `simplify`, `punctuate`, or `translate` (`--to LANG`).
It ships with `pytest` tests (77), a full README, and an MIT license
(`Copyright (c) 2026 Asdale Dynamics, LLC`).

Everything runs on the Python standard library — zero runtime dependencies.

### How it behaves

- Reads source from the clipboard (OS-native tools: `pbcopy/pbpaste`, `wl-copy/wl-paste`,
  `xclip`, `xsel`, Windows PowerShell) or from `--in FILE` / `--stdin`.
- Sends one chat-completion request to `base_url + /chat/completions` with a
  recipe-specific system prompt built locally; the model is requested at
  `temperature 0.2`, non-streaming.
- On success copies the polished text back to the clipboard (`--print` shows it instead).
- **Fail-closed offline**: if the endpoint refuses, times out, returns HTTP errors, or
  malformed JSON, clipolish exits 3 with a plain-English error, and your clipboard,
  files, and history are left completely untouched.
- Config file (TOML) sets `base_url`, `model`, `timeout_seconds`, optional
  `api_key_env`. **No keys are stored or shipped**; auth keys are read from environment
  variables at call time only. Unknown config keys (including an `api_key` key) are
  rejected with an explanation pointing to env vars.
- Optional, **off-by-default** private history log (`--log`): JSONL entries with
  80-character previews first (`--log-full` to store full text), written with mode
  0600 to your platform data dir (`~/.local/share/llm-clipboard-polisher/history.jsonl`
  by default; `$LLM_CLIP_POLISHER_DATA_DIR` overrides).

### Files

- `src/llm_clip_polisher/` — `cli.py` (argparse + flow + exit codes), `config.py`
  (TOML loading/validation), `recipes.py` (4 prompts + message building), `llm.py`
  (urllib request/response, fail-closed), `clipboard.py` (OS-native copy/paste),
  `history.py` (private JSONL log), `__main__.py`.
- `tests/` — 77 tests: unit + end-to-end CLI tests against a local throwaway
  HTTP server that fakes an OpenAI endpoint (success, HTTP 500, malformed JSON,
  closed port), clipboard stubs, history, config, recipes, source-text guards.
- `pyproject.toml`, `README.md`, `LICENSE` (MIT), `.gitignore`.

## How to run

```sh
pip install .               # or: pip install -e . for development
clipolish --template-config # write starter config (base_url defaults to Ollama)
clipolish --show-config     # see exactly what will be used; no recipe needed
clipolish tighten           # clipboard -> clipboard (or capture with xclip first)
clipolish simplify --print
cat file.txt | clipolish punctuate --stdin
clipolish translate --to es
clipolish tighten --log     # also append a private history entry
```

Requirements: Python 3.11+, an OpenAI-compatible endpoint (start Ollama with
`ollama serve`, e.g. model `llama3.1`), and a clipboard tool on Linux
(`wl-copy`/`xclip`/`xsel`); macOS and Windows are built in.

Exit codes: `0` success, `1` usage/input, `2` config, `3` endpoint fail-closed,
`4` clipboard/history unavailable.

## Verification results (2026-11-08)

- `python -m pytest` — **77 passed** (rounds include live-request integration tests
  and deliberate failure modes).
- `ruff check src tests` — **All checks passed** (TRY004 ignored by design:
  user-facing config validation raises `ValueError` deliberately; unused-test
  fixture unpacks ignored via per-file-ignores).
- `ruff format src tests` — clean.
- `python -m build` — sdist and wheel build successfully.
- Manual smoke tests (installed wheel, mock OpenAI-compatible server on
  localhost): tighten/translate roundtrip via `--print` (exit 0, correct system
  prompt model/roles on the wire), offline fail-closed (exit 3, "nothing was
  changed on your machine", clipboard untouched), missing config (exit 2,
  `--template-config` hint), unknown recipe / no recipe / empty or oversized
  source (exit 1 before any network call), `--show-config` and
  `--template-config` without a recipe, and `--log` writing mode-0600 previews
  (no full text) to the data dir.

## Known gaps / next steps

- Clipboard source on Linux requires a wayland/X clipboard helper and a running
  desktop session; headless sessions must use `--in` / `--stdin`. There is no
  pure-Python clipboard fallback (works as intended: no magic background
  daemons, just missing-tool guidance).
- No retry/backoff on transient endpoint failures — one shot per invocation by
  design (a keystroke-friendly tool that returns fast and fails closed).
- No streaming output (`--print` shows the final text only).
- History is append-only; a future `--history` reader or `--clear-history`
  command would round the feature out.
- Only tested against Ollama-style `/v1/chat/completions`; other OpenAI-compatible
  servers (llama.cpp server, LM Studio) are designed-for but unverified locally.
- The system prompts are hand-tuned, not benchmarked; results vary by model.
