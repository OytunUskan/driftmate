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
from typing import Any, Optional

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from driftmate.core.interfaces.build_runner import BuildRunner
from driftmate.core.interfaces.notification_channel import NotificationChannel
from driftmate.core.interfaces.repo_provider import RepoProvider
from driftmate.core.models.build import BuildResult
from driftmate.core.models.notification import Action
from driftmate.core.services.drift_analyzer import (
    DriftAnalyzer,
    DriftReport,
    ManifestError,
)

logger = logging.getLogger(__name__)

YAML_RT = YAML()
YAML_RT.preserve_quotes = True
YAML_RT.indent(mapping=2, sequence=4, offset=2)


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

    def handle_action(self, user_id: str, callback_data: dict[str, Any]) -> None:
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
        try:
            reports = self._analyzer.analyze(self._base_ref)
        except ManifestError as exc:
            logger.error("Analysis failed for user %s: %s", user_id, exc)
            self._notification.sendMessage(f"Analysis failed: {exc}", [])
            return
        except Exception as exc:
            logger.exception("Unexpected error during analysis for user %s", user_id)
            self._notification.sendMessage(
                f"An unexpected error occurred during analysis: {exc}", []
            )
            return

        text = format_report(reports)

        actions = [
            Action(
                id="",
                label=f"Fix {r.component}",
                metadata={
                    "action": "approve",
                    "component": r.component,
                    "target_version": r.upstream_version,
                    "package_file": r.package_file,
                },
            )
            for r in reports
            if r.is_drifted and r.upstream_version != "unknown"
            and not (r.package_file.endswith(".tf") or "terraform" in r.package_file.lower())
        ]
        if actions:
            actions.append(Action(id="", label="Reject", metadata={"action": "reject"}))

        self._notification.sendMessage(text, actions)

    def handle_approve(self, user_id: str, data: dict[str, Any]) -> None:
        component = data.get("component")
        target_version = data.get("target_version")
        package_file = data.get("package_file", "")
        if not component or not target_version:
            self._notification.sendMessage("Invalid approval payload.", [])
            return

        if not package_file:
            package_file = self._manifest_path

        if package_file.endswith(".tf") or "terraform" in package_file.lower():
            self._notification.sendMessage(
                f"Auto-bump not supported for Terraform modules ({component}). Please update manually.",
                [],
            )
            return

        branch = self._repo.createBranch(
            self._branch_name(component), self._base_ref
        )

        current = self._repo.getFile(package_file, self._base_ref)
        updated = bump_package_file(current.content, package_file, component, target_version)

        self._repo.commitFile(
            branch.name,
            package_file,
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

    def handle_reject(self, user_id: str) -> None:
        self._notification.sendMessage(
            "Remediation rejected. No changes made.", []
        )

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

    def _branch_name(self, component: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        slug = "".join(c if c.isalnum() else "-" for c in component.lower())
        return f"{self._branch_prefix}{slug}-{timestamp}"


def format_report(reports: list[DriftReport]) -> str:
    if not reports:
        return "No components configured."
    lines = ["Drift report:"]
    for report in reports:
        if report.is_drifted:
            status = "DRIFT"
        elif report.upstream_version == "unknown" and report.recommendation:
            status = "ERROR"
        else:
            status = "OK"

        pkg_suffix = f" ({report.package_file})" if report.package_file else ""

        if status == "ERROR":
            lines.append(f"- [ERROR] {report.component}{pkg_suffix}: {report.recommendation}")
        elif status == "DRIFT":
            lines.append(
                f"- [DRIFT] {report.component}{pkg_suffix}: "
                f"{report.declared_version} -> {report.upstream_version} "
                f"({report.severity})"
            )
            if report.vuln_summary is not None:
                vs = report.vuln_summary
                lines.append(
                    f"  CVEs: {vs.critical} CRITICAL, {vs.high} HIGH, {vs.medium} MEDIUM, "
                    f"{vs.low} LOW, {vs.unknown} UNKNOWN"
                )
            if report.recommendation and report.recommendation != f"Update {report.component} from {report.declared_version} to {report.upstream_version}.":
                lines.append(f"  Note: {report.recommendation}")
        else:
            lines.append(
                f"- [OK] {report.component}{pkg_suffix}: "
                f"{report.declared_version} -> {report.upstream_version}"
            )
    return "\n".join(lines)


def bump_package_file(
    file_content: str, package_file: str, component: str, target_version: str
) -> str:
    if package_file.endswith("Dockerfile") or "Dockerfile" in package_file:
        lines = file_content.splitlines()
        updated_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith("FROM "):
                tokens = stripped.split()
                image_idx = -1
                for idx in range(1, len(tokens)):
                    if not tokens[idx].startswith("--"):
                        image_idx = idx
                        break
                
                if image_idx != -1:
                    raw_image = tokens[image_idx]
                    parts = raw_image.split(":")
                    image_name = parts[0].split("@")[0]
                    short_image_name = image_name.split("/")[-1]
                    
                    if component in (image_name, short_image_name):
                        digest = ""
                        if "@" in raw_image:
                            digest = "@" + raw_image.split("@", 1)[1]
                        new_image = f"{image_name}:{target_version}{digest}"
                        tokens[image_idx] = new_image
                        indent = line[: len(line) - len(line.lstrip())]
                        line = indent + " ".join(tokens)
            updated_lines.append(line)
        return "\n".join(updated_lines) + "\n"
    elif package_file.endswith("Chart.yaml") or package_file.endswith("Chart.yml"):
        doc = YAML_RT.load(file_content)
        for dep in doc.get("dependencies", []):
            if dep.get("name") == component:
                dep["version"] = DoubleQuotedScalarString(target_version)
        import io
        buf = io.StringIO()
        YAML_RT.dump(doc, buf)
        return buf.getvalue()
    else:
        raise ValueError(f"Unsupported package file format: {package_file}")


def bump_component_version(
    manifest_text: str, component: str, target_version: str
) -> str:
    """Backward-compatible wrapper for driftmate.yaml bumping."""
    try:
        document = YAML_RT.load(manifest_text)
        if document and "components" in document:
            for item in document.get("components", []):
                if item.get("name") == component:
                    item["version"] = DoubleQuotedScalarString(target_version)
                    import io
                    buf = io.StringIO()
                    YAML_RT.dump(document, buf)
                    return buf.getvalue()
    except Exception:
        pass
    return manifest_text
