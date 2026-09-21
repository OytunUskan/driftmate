"""Application entry point.

Bootstraps Driftmate: loads configuration, instantiates the vendor adapters
and wires them into the vendor-agnostic orchestrator.
"""

import logging
import os
import sys
from typing import Callable

from dotenv import load_dotenv

from driftmate.app.init_cmd import run_init
from driftmate.build.local_docker_runner import LocalDockerBuildRunner
from driftmate.channels.common.state_store import InMemoryStateStore
from driftmate.channels.telegram.telegram_channel import TelegramNotificationChannel
from driftmate.config.loader import AppConfig, ConfigError, load_config
from driftmate.core.interfaces.repo_provider import RepoProvider
from driftmate.core.services.drift_analyzer import DriftAnalyzer
from driftmate.core.services.remediation_orchestrator import RemediationOrchestrator
from driftmate.providers.repo.github_provider import GitHubRepoProvider


def build_repo_provider_factory(config: AppConfig) -> Callable[[str, str], RepoProvider]:
    token = config.repositories[0].token

    def factory(owner: str, repo: str) -> RepoProvider:
        return GitHubRepoProvider(token=token, owner=owner, repo=repo)

    return factory


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        run_init()
        return

    load_dotenv()
    configure_logging()

    try:
        config = load_config(os.environ.get("DRIFTMATE_CONFIG", "config.yaml"))
    except ConfigError as exc:
        logging.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    if not config.repositories:
        logging.error("No repositories configured.")
        raise SystemExit(1)

    repo_config = config.repositories[0]

    repo_provider = GitHubRepoProvider(
        token=repo_config.token,
        owner=repo_config.owner,
        repo=repo_config.repo,
    )

    state_store = InMemoryStateStore()

    notification = TelegramNotificationChannel(
        bot_token=config.telegram.bot_token,
        chat_id=config.telegram.chat_id,
        state_store=state_store,
    )

    build_runner = LocalDockerBuildRunner(
        registry=config.build.registry,
        dockerfile=config.build.dockerfile,
        build_context=config.build.build_context,
    )

    analyzer = DriftAnalyzer(
        repo=repo_provider,
        upstream_factory=build_repo_provider_factory(config),
    )

    orchestrator = RemediationOrchestrator(
        repo=repo_provider,
        notification=notification,
        build_runner=build_runner,
        analyzer=analyzer,
        base_ref="main",
        branch_prefix=repo_config.branch_prefix,
        checkout_path=repo_config.checkout_path,
    )

    notification.onAction(orchestrator.handle_action)
    notification.onAnalyze(orchestrator.handle_analyze)

    logging.info("Starting Driftmate (Telegram long-polling)...")
    notification.start()


def configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("DRIFTMATE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":
    main()
