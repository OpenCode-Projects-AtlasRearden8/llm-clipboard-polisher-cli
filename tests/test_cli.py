import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from llm_clip_polisher import cli
from llm_clip_polisher.cli import (
    EXIT_CONFIG,
    EXIT_ENDPOINT,
    EXIT_INPUT,
    EXIT_OK,
    main,
)


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.requests.append(
            {"path": self.path, "headers": dict(self.headers), "body": body}
        )
        mode = self.server.mode
        if mode == "ok":
            payload = {
                "choices": [{"message": {"content": "  Polished: response text\n"}}]
            }
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        elif mode == "http_error":
            detail = json.dumps({"error": {"message": "model not found"}}).encode(
                "utf-8"
            )
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(detail)))
            self.end_headers()
            self.wfile.write(detail)
        elif mode == "malformed":
            self.send_response(200)
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"junk ")


@pytest.fixture()
def fake_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
    server.requests = []
    server.mode = "ok"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    yield server, url, server.requests
    server.shutdown()
    server.server_close()


def write_config(path, base_url, model="test-model"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'base_url = "{base_url}"\nmodel = "{model}"\ntimeout_seconds = 10\n'
    )
    return path


def source_file(tmp_path, text="Here is some rough text."):
    src = tmp_path / "source.txt"
    src.write_text(text, encoding="utf-8")
    return src


def run_online(fake_server, tmp_path, argv_extra=()):
    server, url, requests = fake_server
    config_path = write_config(tmp_path / "config.toml", url)
    code = main(
        [
            "tighten",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(config_path),
            "--print",
            *argv_extra,
        ]
    )
    return code, url, requests


def test_print_success_roundtrip(fake_server, tmp_path, capsys):
    code, url, requests = run_online(fake_server, tmp_path)
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert out.strip() == "Polished: response text"
    assert len(requests) == 1
    assert requests[0]["path"].endswith("/chat/completions")
    sent = requests[0]["body"]
    assert sent["model"] == "test-model"
    assert sent["stream"] is False
    assert sent["temperature"] == 0.2
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][1]["content"] == "Here is some rough text."


def test_stdin_source_reaches_endpoint(fake_server, tmp_path, capsys, monkeypatch):
    server, url, requests = fake_server
    config_path = write_config(tmp_path / "config.toml", url)
    src = tmp_path / "in.txt"
    src.write_text(" hello \n", encoding="utf-8")
    with open(src, encoding="utf-8") as handle:
        monkeypatch.setattr("sys.stdin", handle)
        code = main(["punctuate", "--stdin", "--config", str(config_path), "--print"])
    capsys.readouterr()
    assert code == EXIT_OK
    assert requests[0]["body"]["messages"][1]["content"] == "hello"


def test_clipboard_roundtrip_with_stubs(fake_server, tmp_path, capsys):
    server, url, requests = fake_server
    config_path = write_config(tmp_path / "config.toml", url)
    writes = []
    code = cli.run(
        ["tighten", "--config", str(config_path)],
        environ={},
        read_clipboard_fn=lambda: "  clipboard content  ",
        write_clipboard_fn=lambda text: writes.append(text) or "stub-tool",
    )
    assert code == EXIT_OK
    out, err = capsys.readouterr()
    assert "via stub-tool" in err
    assert requests[0]["body"]["messages"][1]["content"] == "clipboard content"
    assert writes == ["Polished: response text"]


def test_fail_closed_when_endpoint_offline(tmp_path, capsys):
    config_path = write_config(tmp_path / "config.toml", "http://127.0.0.1:1/v1")
    code = main(
        [
            "tighten",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(config_path),
            "--print",
        ]
    )
    assert code == EXIT_ENDPOINT
    err = capsys.readouterr().err
    assert "nothing was changed on your machine" in err
    assert "Ollama" in err


def test_fail_closed_on_http_500(fake_server, tmp_path, capsys):
    server, url, requests = fake_server
    server.mode = "http_error"
    config_path = write_config(tmp_path / "config.toml", url)
    code = main(
        [
            "tighten",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(config_path),
            "--print",
        ]
    )
    assert code == EXIT_ENDPOINT
    assert "HTTP 500" in capsys.readouterr().err


def test_fail_closed_on_malformed_json(fake_server, tmp_path, capsys):
    server, url, requests = fake_server
    server.mode = "malformed"
    config_path = write_config(tmp_path / "config.toml", url)
    code = main(
        [
            "tighten",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(config_path),
            "--print",
        ]
    )
    assert code == EXIT_ENDPOINT
    assert "invalid JSON" in capsys.readouterr().err


def test_fail_closed_leaves_clipboard_untouched(fake_server, tmp_path):
    server, url, requests = fake_server
    server.mode = "http_error"
    config_path = write_config(tmp_path / "config.toml", url)
    writes = []
    with pytest.raises(cli._Exit) as err:
        cli.run(
            [
                "tighten",
                "--in",
                str(source_file(tmp_path)),
                "--config",
                str(config_path),
            ],
            environ={},
            read_clipboard_fn=lambda: "KEEP ME",
            write_clipboard_fn=writes.append,
        )
    assert err.value.code == EXIT_ENDPOINT
    assert writes == []


def test_missing_config_fails_with_exit_2(tmp_path, capsys):
    code = main(
        [
            "tighten",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(tmp_path / "absent.toml"),
            "--print",
        ]
    )
    assert code == EXIT_CONFIG
    assert "no config file found" in capsys.readouterr().err


def test_template_config_hint_in_error(tmp_path, capsys):
    code = main(
        [
            "tighten",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(tmp_path / "absent.toml"),
            "--print",
        ]
    )
    assert "--template-config" in capsys.readouterr().err
    assert code == EXIT_CONFIG


def test_unknown_recipe_returns_input_error():
    code = main(["mystify", "--print"])
    assert code == EXIT_INPUT


def test_translate_requires_to(tmp_path, capsys):
    config_path = write_config(tmp_path / "config.toml", "http://127.0.0.1:1/v1")
    code = main(
        [
            "translate",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(config_path),
            "--print",
        ]
    )
    assert code == EXIT_INPUT
    with_to = main(
        [
            "translate",
            "--to",
            "es",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(config_path),
            "--print",
        ]
    )
    assert with_to == EXIT_ENDPOINT


def test_empty_source_fails_before_endpoint(tmp_path, fake_server):
    server, url, requests = fake_server
    config_path = write_config(tmp_path / "config.toml", url)
    empty = tmp_path / "empty.txt"
    empty.write_text("  \n", encoding="utf-8")
    code = main(
        ["tighten", "--in", str(empty), "--config", str(config_path), "--print"]
    )
    assert code == EXIT_INPUT
    assert requests == []


def test_oversized_source_fails_before_endpoint(tmp_path, fake_server):
    server, url, requests = fake_server
    config_path = write_config(tmp_path / "config.toml", url)
    big = tmp_path / "big.txt"
    big.write_text("x" * 200_000, encoding="utf-8")
    code = main(["tighten", "--in", str(big), "--config", str(config_path), "--print"])
    assert code == EXIT_INPUT
    assert requests == []


def test_show_config_lists_values_without_keys(tmp_path, capsys):
    config_path = write_config(tmp_path / "config.toml", "http://127.0.0.1:1/v1")
    config_path.write_text(
        'base_url = "http://127.0.0.1:1/v1"\nmodel = "m"\napi_key_env = "SOME_KEY_ENV"\n'
    )
    code = main(["tighten", "--show-config", "--config", str(config_path)])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "http://127.0.0.1:1/v1" in out
    assert "SOME_KEY_ENV" in out
    assert "not set" in out


def test_template_config_writes_default(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LLM_CLIP_POLISHER_CONFIG", str(tmp_path / "cfg.toml"))
    code = main(["tighten", "--template-config"])
    assert code == EXIT_OK
    written = tmp_path / "cfg.toml"
    assert written.exists()
    assert "base_url" in written.read_text()
    code_again = main(["tighten", "--template-config"])
    assert code_again == EXIT_OK


def test_history_log_previews_only(fake_server, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LLM_CLIP_POLISHER_DATA_DIR", str(tmp_path / "data"))
    code, url, requests = run_online(fake_server, tmp_path, argv_extra=("--log",))
    assert code == EXIT_OK
    history = tmp_path / "data" / "history.jsonl"
    assert history.exists()
    entry = json.loads(history.read_text(encoding="utf-8").splitlines()[0])
    assert entry["recipe"] == "tighten"
    assert entry["model"] == "test-model"
    assert entry["target_language"] is None
    assert entry["source_preview"] == "Here is some rough text."
    assert entry["full_text_stored"] is False
    assert "previews only" in capsys.readouterr().err


def test_history_log_full_text(fake_server, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LLM_CLIP_POLISHER_DATA_DIR", str(tmp_path / "data"))
    code, url, requests = run_online(
        fake_server, tmp_path, argv_extra=("--log", "--log-full")
    )
    assert code == EXIT_OK
    history = tmp_path / "data" / "history.jsonl"
    entry = json.loads(history.read_text(encoding="utf-8").splitlines()[0])
    assert entry["full_text_stored"] is True
    assert "full text" in capsys.readouterr().err


def test_two_sources_rejected(tmp_path):
    config_path = write_config(tmp_path / "config.toml", "http://127.0.0.1:1/v1")
    code = main(
        [
            "tighten",
            "--stdin",
            "--in",
            str(source_file(tmp_path)),
            "--config",
            str(config_path),
            "--print",
        ]
    )
    assert code == EXIT_INPUT


def test_help_lists_recipes_and_examples(capsys):
    with pytest.raises(SystemExit) as err:
        cli.build_parser().parse_args(["--help"])
    assert err.value.code == 0
    out = capsys.readouterr().out
    assert "tighten" in out
    assert "translate" in out
    assert "clipolish tighten" in out


def test_show_config_without_recipe(tmp_path, capsys):
    config_path = write_config(tmp_path / "config.toml", "http://127.0.0.1:1/v1")
    code = main(["--show-config", "--config", str(config_path)])
    assert code == EXIT_OK
    assert "http://127.0.0.1:1/v1" in capsys.readouterr().out


def test_template_config_without_recipe(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LLM_CLIP_POLISHER_CONFIG", str(tmp_path / "cfg.toml"))
    code = main(["--template-config"])
    assert code == EXIT_OK
    assert (tmp_path / "cfg.toml").exists()


def test_no_recipe_is_input_error(capsys):
    code = main(["--print"])
    assert code == EXIT_INPUT
    assert "no recipe given" in capsys.readouterr().err
