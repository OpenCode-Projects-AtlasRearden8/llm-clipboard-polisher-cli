# clipolish (llm-clipboard-polisher)

Privacy-first clipboard polisher for local AI. Copy some text, run one command, get polished text back on your clipboard — no cloud, no accounts, no data harvesting.

**Text travels exactly two places: your clipboard and the endpoint in your own config file (Ollama and other OpenAI-compatible local servers). That's it.**

Made by [Asdale Dynamics, LLC](https://dylanasdale.github.io) — AI explained like a friend would.

## What it does

`clipolish` takes text (usually straight from your clipboard) and asks your locally configured, OpenAI-compatible endpoint to apply **one rewrite recipe**:

| Recipe | What it does |
|---|---|
| `tighten` | Trim filler and padding so the text says the same thing in fewer words |
| `simplify` | Rewrite in plain English, the way a friendly teacher would — never condescending |
| `punctuate` | Fix punctuation, capitalization, and light grammar only (no rewording) |
| `translate` | Translate into a language you pick with `--to` |

## Requirements

- Python 3.11+ (uses only the standard library — no `pip` dependencies at runtime)
- A local OpenAI-compatible chat endpoint, e.g. Ollama:
  - Ollama serves `http://127.0.0.1:11434/v1` out of the box; start it with `ollama serve` and pull a model, e.g. `ollama pull llama3.1`
- A clipboard tool for headless copy/paste on Linux (`wl-copy` on Wayland, or `xclip`/`xsel`); macOS (`pbcopy`/`pbpaste`) and Windows (PowerShell) already have them built in

## Install

```sh
pip install .
```

or run straight from a checkout:

```sh
pip install -e .
```

## Configure

There are **no baked-in API keys**. Copy/paste URL and model live in one small TOML file. Either write it yourself or generate a template:

```sh
clipolish --template-config
```

`~/.config/llm-clipboard-polisher/config.toml`:

```toml
base_url = "http://127.0.0.1:11434/v1"   # Ollama defaults work as-is
model = "llama3.1"
timeout_seconds = 60
# api_key_env = "POLISHER_API_KEY"       # only if your endpoint needs a key
```

Config locations: `--config FILE`, or `$LLM_CLIP_POLISHER_CONFIG`, or the default path above under `$XDG_CONFIG_HOME` (Linux), `~/Library/Application Support` (macOS), `%APPDATA%` (Windows).

**Keys stay out of the file.** If your endpoint wants auth, set an environment variable and point `api_key_env` at its name (`POLISHER_API_KEY` by default). The key is read at runtime and never written to disk by clipolish.

Check what you're actually running with:

```sh
clipolish --show-config
```

## Use it

```sh
clipolish tighten            # clipboard -> clipboard (source clipboard is only replaced on success)
clipolish simplify            # plain-English rewrite
clipolish punctuate --in mail.txt --print   # read a file, print result instead of copying
cat rough.txt | clipolish punctuate --stdin
clipolish translate --to es   # clipboard text into Spanish (or de, fr, ja, ...)
clipolish tighten --log       # also append a private local history entry
```

Useful everywhere:

- `--print` — show the result instead of touching the clipboard
- `--log` — off by default; with it, clipolish appends a JSONL entry to your history file with 80-character previews first; add `--log-full` to store full text
- `--template-config` — write a starter config and exit

## Failure is fail-closed

If the endpoint is offline, times out, or errors, clipolish **stops and changes nothing** — your clipboard keeps the original text, nothing is logged, and you get a plain-English error:

```
clipolish: endpoint error (nothing was changed on your machine): could not reach
http://127.0.0.1:11434/v1 (URLError: ...). Is your local server (for example Ollama) running?
```

Exit codes make it script-friendly: `0` success, `1` usage/input, `2` config, `3` endpoint (fail-closed), `4` clipboard unavailable.

## Privacy checklist

- No telemetry, no analytics, no third-party HTTP calls — networking is one request to your configured base URL, using only `urllib` from the standard library
- CLI flags beat environment beats config file: nothing is learned behind your back; `--show-config` shows every effective value
- History logging is opt-in and previews-only by default; the log file is chmod `0600`
- Source text runs through one prompt built locally; no prompt is ever sent twice or "prefetched"
- API keys never live in config files; they come from environment variables at call time

## Development

```sh
python -m pip install -e .
python -m pip install pytest build
python -m pytest              # run the test suite (offline, no local model needed)
python -m build               # build sdist + wheel
```

The tests include live integration checks against a local throwaway HTTP server that fakes an OpenAI-compatible endpoint, plus a deliberately closed port to prove fail-closed behavior. No real clipboard changes happen during tests (Linux tests use injectable flag/tool stubs).

## How this fits the family

- `llm-clipboard-polisher` (this tool): one quick rewrite for text you've already written
- `jargon-simplifier-cli`: converts jargon into plain language in a single consistent style
- `llm-diff-explainer-cli`: explains what changed in code diffs
- Hub: [dylanasdale.github.io](https://dylanasdale.github.io) · Book: *The Massive AI Manual*

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Asdale Dynamics, LLC.
