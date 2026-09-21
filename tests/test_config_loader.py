import pytest

from driftmate.config.loader import ConfigError, build_config, resolve_env_vars


def _raw_config():
    return {
        "app": {"log_level": "INFO"},
        "repositories": [
            {
                "name": "driftmate",
                "provider": "github",
                "owner": "o",
                "repo": "r",
                "token_env": "GITHUB_TOKEN",
            }
        ],
        "notification": {
            "channel": "telegram",
            "telegram": {
                "bot_token_env": "TELEGRAM_BOT_TOKEN",
                "chat_id_env": "TELEGRAM_CHAT_ID",
            },
        },
        "build": {
            "runner": "local_docker",
            "registry": {
                "url_env": "DOCKER_REGISTRY_URL",
                "username_env": "DOCKER_USERNAME",
                "password_env": "DOCKER_PASSWORD",
            },
        },
    }


def test_missing_required_env_raises(monkeypatch):
    for name in ["GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        monkeypatch.delenv(name, raising=False)
    raw = _raw_config()
    with pytest.raises(ConfigError):
        resolve_env_vars(raw)


def test_registry_env_vars_are_optional(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "b")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    for name in ["DOCKER_REGISTRY_URL", "DOCKER_USERNAME", "DOCKER_PASSWORD"]:
        monkeypatch.delenv(name, raising=False)

    raw = _raw_config()
    resolve_env_vars(raw)
    config = build_config(raw)

    assert config.repositories[0].token == "t"
    assert config.build.registry.url is None
    assert config.build.registry.username is None
    assert config.build.registry.password is None
