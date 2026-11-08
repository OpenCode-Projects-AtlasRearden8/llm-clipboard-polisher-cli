import json

import pytest

from llm_clip_polisher.config import MAX_SOURCE_CHARS, PolisherConfig
from llm_clip_polisher.llm import (
    EndpointError,
    build_request_body,
    chat_completion_url,
    extract_reply,
    normalize_source_text,
    polish_text,
)


def test_normalize_strips_and_bounds():
    assert normalize_source_text("  hello \n\t") == "hello"
    with pytest.raises(ValueError, match="nothing to polish"):
        normalize_source_text("   \n")
    with pytest.raises(ValueError, match="limit is"):
        normalize_source_text("x" * (MAX_SOURCE_CHARS + 1))


def test_url_is_openai_chat_completions():
    config = PolisherConfig(base_url="http://127.0.0.1:11434/v1")
    assert chat_completion_url(config) == "http://127.0.0.1:11434/v1/chat/completions"


def test_request_body_shape():
    config = PolisherConfig(model="llama3.1")
    body = build_request_body(config, [{"role": "user", "content": "hi"}])
    assert body["model"] == "llama3.1"
    assert body["stream"] is False
    assert body["messages"][0]["role"] == "user"


def test_extract_reply_happy_path():
    payload = {"choices": [{"message": {"content": "Polished text\n"}}]}
    assert extract_reply(payload) == "Polished text"


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
        {"nope": True},
        "not a dict",
    ],
)
def test_extract_reply_rejects_malformed(payload):
    with pytest.raises(EndpointError):
        extract_reply(payload)


def test_extract_reply_rejects_empty_text():
    with pytest.raises(EndpointError, match="empty"):
        extract_reply({"choices": [{"message": {"content": "   "}}]})


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_polish_text_sends_expected_request_and_parses(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        assert timeout == 5.0
        return _FakeResponse(
            json.dumps({"choices": [{"message": {"content": "Tightened."}}]}).encode()
        )

    monkeypatch.setattr("llm_clip_polisher.llm.urllib.request.urlopen", fake_urlopen)
    config = PolisherConfig(
        base_url="http://127.0.0.1:9999/v1",
        model="m",
        timeout_seconds=5.0,
        api_key="zz",
    )
    result = polish_text(config, [{"role": "user", "content": "hi"}])
    assert result == "Tightened."
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer zz"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"]["model"] == "m"


def test_polish_text_http_error_fails_closed(monkeypatch):
    import urllib.error

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, None)

    monkeypatch.setattr("llm_clip_polisher.llm.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(EndpointError, match="HTTP 500"):
        polish_text(PolisherConfig(), [{"role": "user", "content": "hi"}])


def test_polish_text_unreachable_fails_closed():
    config = PolisherConfig(base_url="http://127.0.0.1:1/v1", timeout_seconds=0.5)
    with pytest.raises(EndpointError) as err:
        polish_text(config, [{"role": "user", "content": "hi"}])
    message = str(err.value)
    assert "could not reach" in message
    assert "Ollama" in message


def test_polish_text_invalid_json_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "llm_clip_polisher.llm.urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(b"not json"),
    )
    with pytest.raises(EndpointError, match="invalid JSON"):
        polish_text(PolisherConfig(), [{"role": "user", "content": "hi"}])
