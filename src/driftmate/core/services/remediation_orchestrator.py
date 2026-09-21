"""Vendor-agnostic remediation orchestration.

Coordinates the analyze -> propose -> approve -> fix flow using only the
RepoProvider, NotificationChannel and BuildRunner abstractions. The
orchestrator is stateless: short-ID -> context mapping is the responsibility
of the channel adapter and is never touched here.
"""

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

import yaml

from driftmate.core.interfaces.build_runner import BuildRunner
from driftmate.core.interfaces.notification_channel import NotificationChannel
from driftmate.core.interfaces.repo_provider import RepoProvider
from driftmate.core.models.build import BuildResult
from driftmate.core.models.notification import Action
from driftmate.core.services.drift_analyzer import DriftAnalyzer, DriftReport

logger = logging.getLogger(__name__)


class RemediationOrchestrator:
    def __init__(
        self,
        repo: RepoProvider,
        notification: NotificationChannel,
        build_runner: BuildRunner,
        analyzer: DriftAnalyzer,
        manifest_path: str = "driftmate.yaml",
        base_ref: str = "main",
        branch_prefix: str = "drift-",
        checkout_path: Optional[str] = None,
    ) -> None:
        self._repo = repo
        self._notification = notification
        self._build_runner = build_runner
        self._analyzer = analyzer
        self._manifest_path = manifest_path
        self._base_ref = base_ref
        self._branch_prefix = branch_prefix
        self._checkout_path = checkout_path

    def handle_action(self, user_id: str, callback_data: dict) -> None:
        action = callback_data.get("action")
        if action == "analyze":
            self.handle_analyze(user_id)
        elif action == "approve":
            self.handle_approve(user_id, callback_data)
        elif action == "reject":
            self.handle_reject(user_id)
        else:
            self._notification.sendMessage(f"Unknown action: {action!r}", [])

    def handle_analyze(self, user_id: str) -> None:
        reports = self._analyzer.analyze(self._base_ref)
        text = format_report(reports)

        actions = [
            Action(
                id="",
                label=f"Fix {r.component}",
                metadata={
                    "action": "approve",
                    "component": r.component,
                    "target_version": r.upstream_version,
                },
            )
            for r in reports
            if r.is_drifted and r.upstream_version != "unknown"
        ]
        if actions:
            actions.append(Action(id="", label="Reject", metadata={"action": "reject"}))

        self._notification.sendMessage(text, actions)

    def handle_approve(self, user_id: str, data: dict) -> None:
        component = data.get("component")
        target_version = data.get("target_version")
        if not component or not target_version:
            self._notification.sendMessage("Invalid approval payload.", [])
            return

        branch = self._repo.createBranch(
            self._branch_name(component), self._base_ref
        )

        current = self._repo.getFile(self._manifest_path, self._base_ref)
        updated = bump_component_version(current.content, component, target_version)

        self._repo.commitFile(
            branch.name,
            self._manifest_path,
            updated,
            f"chore(drift): bump {component} to {target_version}",
        )

        remote_ref = self._repo.publishBranch(branch)

        image_tag = f"{component}:{target_version}"
        build_result = self._build_fix(remote_ref.name, image_tag)

        if build_result is not None:
            text = (
                f"Fix for {component} applied on branch `{branch.name}`.\n"
                f"Build status: {build_result.status.value}\n"
                f"Remote: {remote_ref.url}"
            )
        else:
            text = (
                f"Fix for {component} applied on branch `{branch.name}`.\n"
                f"Build skipped: checkout_path not configured.\n"
                f"Remote: {remote_ref.url}"
            )

        self._notification.sendMessage(text, [])

    def _build_fix(
        self, branch_name: str, image_tag: str
    ) -> Optional[BuildResult]:
        worktree_path = self._prepare_worktree(branch_name)
        if worktree_path is None:
            logger.error(
                "Build skipped for %s: checkout_path not configured.", branch_name
            )
            return None

        try:
            return self._build_runner.build(
                branch_name, image_tag, context_path=worktree_path
            )
        finally:
            if worktree_path:
                self._cleanup_worktree(worktree_path)

    def _prepare_worktree(self, branch_name: str) -> Optional[str]:
        if not self._checkout_path:
            logger.warning(
                "No checkout_path configured; building from default context."
            )
            return None

        worktree_path = os.path.join("/tmp", f"driftmate-build-{branch_name}")
        try:
            subprocess.run(
                ["git", "fetch", "origin", branch_name],
                cwd=self._checkout_path,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "worktree", "add", worktree_path, branch_name],
                cwd=self._checkout_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.error("Failed to prepare worktree for %s: %s", branch_name, exc)
            return None
        return worktree_path

    def _cleanup_worktree(self, worktree_path: str) -> None:
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                cwd=self._checkout_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.error("Failed to clean up worktree %s: %s", worktree_path, exc)

    def handle_reject(self, user_id: str) -> None:
        self._notification.sendMessage(
            "Remediation rejected. No changes made.", []
        )

    def _branch_name(self, component: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        slug = "".join(c if c.isalnum() else "-" for c in component.lower())
        return f"{self._branch_prefix}{slug}-{timestamp}"


def format_report(reports: list[DriftReport]) -> str:
    if not reports:
        return "No components configured."
    lines = ["Drift report:"]
    for report in reports:
        status = "DRIFT" if report.is_drifted else "OK"
        lines.append(
            f"- [{status}] {report.component}: "
            f"{report.declared_version} -> {report.upstream_version} "
            f"({report.severity})"
        )
    return "\n".join(lines)


def bump_component_version(
    manifest_text: str, component: str, target_version: str
) -> str:
    data = yaml.safe_load(manifest_text)
    if not isinstance(data, dict):
        raise ValueError("Manifest is not a mapping")
    for item in data.get("components", []):
        if item.get("name") == component:
            item["version"] = target_version
            return yaml.safe_dump(data, sort_keys=False)
    raise ValueError(f"Component {component!r} not found in manifest")
