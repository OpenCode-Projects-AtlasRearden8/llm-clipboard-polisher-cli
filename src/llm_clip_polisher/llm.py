"""OpenAI-compatible chat completion call. Stdlib only, fails closed offline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .config import MAX_SOURCE_CHARS, PolisherConfig


class EndpointError(Exception):
    """The local endpoint could not be reached or returned an error."""


def normalize_source_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("nothing to polish: the source text is empty")
    if len(stripped) > MAX_SOURCE_CHARS:
        raise ValueError(
            f"source text is {len(stripped)} characters; "
            f"the limit is {MAX_SOURCE_CHARS} to keep local models safe"
        )
    return stripped


def chat_completion_url(config: PolisherConfig) -> str:
    return f"{config.base_url.rstrip('/')}/chat/completions"


def build_request_body(
    config: PolisherConfig, messages: list[dict], temperature: float = 0.2
) -> dict:
    return {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }


def extract_reply(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise EndpointError("endpoint returned an unexpected JSON shape")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise EndpointError("endpoint response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise EndpointError("endpoint response has a malformed choice")
    message = first.get("message")
    if not isinstance(message, dict):
        raise EndpointError("endpoint response is missing the message field")
    content = message.get("content")
    if not isinstance(content, str):
        raise EndpointError("endpoint response message has no text content")
    cleaned = content.strip()
    if not cleaned:
        raise EndpointError("endpoint returned empty text")
    return cleaned


def polish_text(config: PolisherConfig, messages: list[dict]) -> str:
    payload = build_request_body(config, messages)
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        chat_completion_url(config),
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            **config.auth_header(),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=config.timeout_seconds
        ) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:500]
        except OSError:
            detail = ""
        raise EndpointError(
            f"endpoint returned HTTP {exc.code} for {config.base_url}"
            + (f": {detail}" if detail else "")
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EndpointError(
            f"could not reach {config.base_url} ({exc.__class__.__name__}: {exc}). "
            "Is your local server (for example Ollama) running?"
        ) from exc
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EndpointError(f"endpoint returned invalid JSON ({exc})") from exc
    return extract_reply(parsed)
