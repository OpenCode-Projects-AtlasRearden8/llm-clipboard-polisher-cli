import pytest

from llm_clip_polisher.config import (
    ENV_API_KEY,
    PolisherConfig,
    default_config_text,
    load_config,
    load_config_from_dict,
    write_template_config,
)


def test_default_template_parses():
    import tomllib

    data = tomllib.loads(default_config_text())
    config = load_config_from_dict(data)
    assert config.base_url == "http://127.0.0.1:11434/v1"
    assert config.model == "llama3.1"
    assert config.timeout_seconds == 60.0
    assert config.api_key is None


def test_unknown_keys_rejected_with_key_hint():
    with pytest.raises(ValueError) as err:
        load_config_from_dict({"base_url": "http://x/v1", "api_key": "sk-secret"})
    assert "api_key" in str(err.value)
    assert "environment" in str(err.value)


def test_base_url_normalization():
    config = load_config_from_dict(
        {"base_url": "http://host:8080/v1/chat/completions///"}
    )
    assert config.base_url == "http://host:8080/v1"


@pytest.mark.parametrize(
    "bad",
    [
        ("ftp://host/v1", "must start"),
        ("127.0.0.1:11434", "must start"),
        ("", "non-empty"),
    ],
)
def test_base_url_rejects_bad_values(bad):
    value, expected = bad
    with pytest.raises(ValueError, match=expected):
        load_config_from_dict({"base_url": value})


@pytest.mark.parametrize("bad", [True, "fast", 0, -3])
def test_timeout_rejects_bad_values(bad):
    with pytest.raises(ValueError, match="timeout_seconds"):
        load_config_from_dict({"timeout_seconds": bad})


def test_missing_config_raises_file_not_found_with_hint(tmp_path):
    missing = tmp_path / "nope.toml"
    with pytest.raises(FileNotFoundError, match="no config file found") as err:
        load_config(explicit_path=missing)
    assert "--template-config" in str(err.value)
    with pytest.raises(FileNotFoundError):
        load_config(explicit_path=missing / "deeper.toml")


def test_write_template_config_creates_file_once(tmp_path):
    target = tmp_path / "sub" / "config.toml"
    written = write_template_config(target)
    assert written == target
    text = target.read_text()
    assert "base_url" in text and "api_key_env" in text
    first_mtime = target.stat().st_mtime_ns
    write_template_config(target)
    assert target.stat().st_mtime_ns == first_mtime


def test_api_key_from_env(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'base_url = "http://x/v1"\nmodel = "m"\napi_key_env = "MY_TEST_KEY"\n'
    )
    config = load_config(config_path, environ={"MY_TEST_KEY": "abc123"})
    assert config.api_key == "abc123"
    assert config.auth_header() == {"Authorization": "Bearer abc123"}


def test_api_key_missing_env_means_no_header(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('base_url = "http://x/v1"\nmodel = "m"\n')
    config = load_config(config_path, environ={})
    assert config.api_key is None
    assert config.auth_header() == {}


def test_api_key_empty_env_fails_closed(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('base_url = "http://x/v1"\nmodel = "m"\n')
    with pytest.raises(ValueError, match="set but empty"):
        load_config(config_path, environ={ENV_API_KEY: "  "})


def test_default_api_key_env_name():
    config = PolisherConfig()
    assert config.api_key_env_name() == ENV_API_KEY
