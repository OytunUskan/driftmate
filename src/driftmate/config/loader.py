"""Configuration loading and environment variable resolution.

Reads config.yaml and resolves any key ending in '_env' from the process
environment. Secret values are never stored in config.yaml; they are
referenced by environment variable name. The '_env' suffix is stripped from
the key so that the resolved value lands on the base field name.
"""

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when configuration is invalid or a required env var is missing."""


@dataclass
class RepositoryConfig:
    name: str
    provider: str
    owner: str
    repo: str
    token: str = ""
    branch_prefix: str = "drift-"
    checkout_path: str | None = None


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class RegistryConfig:
    url: str | None = None
    username: str | None = None
    password: str | None = None


@dataclass
class BuildConfig:
    runner: str = "local_docker"
    dockerfile: str = "Dockerfile"
    build_context: str = "."
    tag_separator: str = "-"
    registry: RegistryConfig = field(default_factory=RegistryConfig)


@dataclass
class RemediationConfig:
    auto_branch: bool = True
    require_approval: bool = True
    max_parallel_builds: int = 2


@dataclass
class AppConfig:
    log_level: str = "INFO"
    repositories: list[RepositoryConfig] = field(default_factory=list)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    remediation: RemediationConfig = field(default_factory=RemediationConfig)
    state_store: str = "in-memory"


def load_config(path: str = "config.yaml") -> AppConfig:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    resolve_env_vars(raw)
    return build_config(raw)


def resolve_env_vars(node: Any, required: bool = True) -> None:
    if isinstance(node, dict):
        for key in list(node.keys()):
            value = node[key]
            if isinstance(value, str) and key.endswith("_env"):
                resolved = _lookup_env(value, key, required=required)
                node[key[:-4]] = resolved
                del node[key]
            else:
                resolve_env_vars(value, required=(required and key != "registry"))
    elif isinstance(node, list):
        for item in node:
            resolve_env_vars(item, required=required)


def build_config(raw: dict) -> AppConfig:
    app = raw.get("app", {}) or {}
    config = AppConfig(log_level=app.get("log_level", "INFO"))

    for repo_raw in raw.get("repositories", []) or []:
        config.repositories.append(
            RepositoryConfig(
                name=repo_raw["name"],
                provider=repo_raw["provider"],
                owner=repo_raw["owner"],
                repo=repo_raw["repo"],
                token=repo_raw.get("token", ""),
                branch_prefix=repo_raw.get("branch_prefix", "drift-"),
                checkout_path=repo_raw.get("checkout_path") or None,
            )
        )

    notification = raw.get("notification", {}) or {}
    telegram = notification.get("telegram", {}) or {}
    config.telegram = TelegramConfig(
        bot_token=telegram.get("bot_token", ""),
        chat_id=telegram.get("chat_id", ""),
    )

    build_raw = raw.get("build", {}) or {}
    registry_raw = build_raw.get("registry", {}) or {}
    config.build = BuildConfig(
        runner=build_raw.get("runner", "local_docker"),
        dockerfile=build_raw.get("dockerfile", "Dockerfile"),
        build_context=build_raw.get("build_context", "."),
        tag_separator=build_raw.get("tag_separator", "-"),
        registry=RegistryConfig(
            url=registry_raw.get("url"),
            username=registry_raw.get("username"),
            password=registry_raw.get("password"),
        ),
    )

    remediation = raw.get("remediation", {}) or {}
    config.remediation = RemediationConfig(
        auto_branch=remediation.get("auto_branch", True),
        require_approval=remediation.get("require_approval", True),
        max_parallel_builds=remediation.get("max_parallel_builds", 2),
    )

    state = raw.get("state", {}) or {}
    config.state_store = state.get("store", "in-memory")

    return config


def _lookup_env(env_name: str, key: str, required: bool = True) -> str | None:
    value = os.environ.get(env_name)
    if value is None and required:
        raise ConfigError(
            f"Environment variable '{env_name}' is not set "
            f"(required by config key '{key}')."
        )
    return value
