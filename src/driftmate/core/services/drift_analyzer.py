"""Vendor-agnostic drift detection powered by Renovate CLI."""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import yaml

from driftmate.core.interfaces.repo_provider import RepoProvider
from driftmate.core.models.repo import Content
from driftmate.core.services.renovate_runner import RenovateRunner, RenovateError

logger = logging.getLogger(__name__)


class Severity(Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ComponentSpec:
    name: str
    version: str
    upstream_owner: str = ""
    upstream_repo: str = ""
    upstream_path: str = ""
    upstream_ref: str = "main"
    version_key: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DriftReport:
    component: str
    declared_version: str
    upstream_version: str
    is_drifted: bool = False
    severity: str = Severity.NONE.value
    recommendation: str = ""
    package_file: str = ""


@dataclass
class Manifest:
    components: list[ComponentSpec] = field(default_factory=list)


class ManifestError(Exception):
    """Raised when manifest file cannot be fetched or parsed or Renovate execution fails."""


class ManifestNotFoundError(ManifestError):
    """Raised when manifest file is not found at the specified ref."""


class DriftAnalyzer:
    def __init__(
        self,
        repo: Optional[RepoProvider] = None,
        upstream_factory: Optional[Callable[[str, str], RepoProvider]] = None,
        manifest_path: str = "driftmate.yaml",
        checkout_path: Optional[str] = None,
        renovate_runner: Optional[RenovateRunner] = None,
    ) -> None:
        self._repo = repo
        self._upstream_factory = upstream_factory
        self._manifest_path = manifest_path
        self._checkout_path = checkout_path or os.getcwd()
        self._renovate_runner = renovate_runner or RenovateRunner()

    def analyze(self, ref: str = "main") -> list[DriftReport]:
        if not self._renovate_runner.check_health():
            raise ManifestError(
                "Renovate CLI is not installed or not healthy. Run 'npm install -g renovate'."
            )

        try:
            result = self._renovate_runner.run_lookup(self._checkout_path)
        except RenovateError as exc:
            raise ManifestError(str(exc)) from exc
        except Exception as exc:
            raise ManifestError(f"Renovate lookup failed: {exc}") from exc

        reports: list[DriftReport] = []
        for dep in result.dependencies:
            upstream = dep.new_value if dep.new_value else dep.current_value
            report = compare_versions(dep.name, dep.current_value, upstream)
            report.package_file = dep.package_file
            
            if dep.package_file.endswith(".tf") or dep.datasource == "terraform-module":
                if report.is_drifted:
                    report.recommendation += " (Terraform module bump: manual update required)"
            
            reports.append(report)

        return reports


def parse_manifest(content: str) -> Manifest:
    data = yaml.safe_load(content) or {}
    components: list[ComponentSpec] = []
    for item in data.get("components", []):
        name = str(item.get("name", ""))
        raw_version = item.get("version")
        if not isinstance(raw_version, str):
            components.append(
                ComponentSpec(
                    name=name,
                    version="",
                    error="version field must be quoted",
                )
            )
            continue
        upstream = item.get("upstream", {}) or {}
        components.append(
            ComponentSpec(
                name=name,
                version=raw_version,
                upstream_owner=str(upstream.get("owner", "")),
                upstream_repo=str(upstream.get("repo", "")),
                upstream_path=str(upstream.get("path", "")),
                upstream_ref=str(upstream.get("ref", "main")),
                version_key=upstream.get("version_key"),
            )
        )
    return Manifest(components=components)


def extract_version(content: Content, version_key: Optional[str]) -> str:
    if content.is_binary:
        return ""
    if version_key is None:
        return content.content.strip()
    data = yaml.safe_load(content.content)
    if not isinstance(data, dict):
        return ""
    value = data.get(version_key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(
            f"upstream version field {version_key!r} must be a quoted string; "
            f"got {type(value).__name__} ({value!r})"
        )
    return value.strip()


def compare_versions(component: str, declared: str, upstream: str) -> DriftReport:
    try:
        declared_tuple = _parse_version(declared)
    except ValueError:
        return DriftReport(
            component=component,
            declared_version=declared,
            upstream_version=upstream,
            is_drifted=False,
            severity=Severity.NONE.value,
            recommendation=f"declared version unparseable: {declared}",
        )

    try:
        upstream_tuple = _parse_version(upstream)
    except ValueError:
        return DriftReport(
            component=component,
            declared_version=declared,
            upstream_version=upstream,
            is_drifted=False,
            severity=Severity.NONE.value,
            recommendation=f"upstream version unparseable: {upstream}",
        )

    if declared_tuple == upstream_tuple:
        return DriftReport(
            component=component,
            declared_version=declared,
            upstream_version=upstream,
            is_drifted=False,
            severity=Severity.NONE.value,
            recommendation="",
        )

    if upstream_tuple > declared_tuple:
        severity = _severity_for_gap(declared_tuple, upstream_tuple)
        recommendation = f"Update {component} from {declared} to {upstream}."
    else:
        severity = Severity.LOW
        recommendation = (
            f"{component} is pinned ahead of upstream "
            f"({declared} > {upstream}). Verify intent."
        )

    return DriftReport(
        component=component,
        declared_version=declared,
        upstream_version=upstream,
        is_drifted=True,
        severity=severity.value,
        recommendation=recommendation,
    )


def _parse_version(version: str) -> tuple[int, int, int]:
    cleaned = version.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = cleaned.split(".")
    try:
        major = int(parts[0]) if parts[0] else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError as exc:
        raise ValueError(f"unparseable version: {version!r}") from exc
    return major, minor, patch


def _severity_for_gap(
    declared: tuple[int, int, int],
    upstream: tuple[int, int, int],
) -> Severity:
    if upstream[0] > declared[0]:
        return Severity.CRITICAL
    if upstream[1] > declared[1]:
        return Severity.HIGH
    return Severity.MEDIUM
