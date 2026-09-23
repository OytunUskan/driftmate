"""Application entry point.

Bootstraps Driftmate: loads configuration, instantiates the vendor adapters
and wires them into the vendor-agnostic orchestrator.
"""

import argparse
import logging
import os
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

from driftmate.app.init_cmd import run_init
from driftmate.app.scan_cmd import run_scan
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
    parser = argparse.ArgumentParser(
        prog="driftmate",
        description="Driftmate — dependency version drift detection and human-approved remediation for Dockerfiles, Helm charts, and Terraform modules.",
        add_help=True,
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Run interactive setup.")

    scan_parser = subparsers.add_parser("scan", help="Scan local path for drift without tokens.")
    scan_parser.add_argument("path", nargs="?", default=None, help="Path to scan (defaults to cwd).")
    scan_parser.add_argument("-o", "--output", default=None, help="Output markdown report path.")
    scan_parser.add_argument("--cve", action="store_true", default=False, help="Enable container vulnerability scanning (adds ~60-120s per image).")
    scan_parser.add_argument("--cve-target", default=None, help="Only scan the specified package file path (implies --cve).")

    args = parser.parse_args()

    if args.command == "init":
        run_init()
        return

    if args.command == "scan":
        scan_cve = args.cve or bool(args.cve_target)
        run_scan(path=args.path, output=args.output, scan_cve=scan_cve, cve_target=args.cve_target)
        return

    dotenv_path = Path.cwd() / ".env"
    if not dotenv_path.is_file():
        raise SystemExit(
            f"'.env' not found in {Path.cwd()}. Run 'driftmate init' first, "
            "or export the required environment variables directly."
        )
    loaded = load_dotenv(dotenv_path=dotenv_path)
    if not loaded:
        raise SystemExit(
            f"'.env' not found in {Path.cwd()}. Run 'driftmate init' first, "
            "or export the required environment variables directly."
        )

    configure_logging()

    logging.info("GITHUB_TOKEN set: %s", bool(os.environ.get("GITHUB_TOKEN")))

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
        checkout_path=repo_config.checkout_path,
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
