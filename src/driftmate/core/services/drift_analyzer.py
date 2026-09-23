"""Vendor-agnostic drift detection powered by Renovate CLI."""

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import yaml

from driftmate.core.interfaces.repo_provider import RepoProvider
from driftmate.core.models.repo import Content
from driftmate.core.services.renovate_runner import RenovateRunner, RenovateError
from driftmate.core.services.trivy_runner import TrivyRunner, VulnSummary
from driftmate.core.services.field_diff import FieldDiff, compute_field_diff

logger = logging.getLogger(__name__)


class Severity(Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class DriftReport:
    component: str
    declared_version: str
    upstream_version: str
    is_drifted: bool = False
    severity: str = Severity.NONE.value
    recommendation: str = ""
    package_file: str = ""
    vuln_summary: Optional[VulnSummary] = None
    field_diff: Optional[FieldDiff] = None
    registry_url: Optional[str] = None


class ManifestError(Exception):
    """Raised when repository scanning or Renovate execution fails."""


class ManifestNotFoundError(ManifestError):
    """Raised when repository path is not found."""


class DriftAnalyzer:
    def __init__(
        self,
        repo: Optional[RepoProvider] = None,
        upstream_factory: Optional[Callable[[str, str], RepoProvider]] = None,
        manifest_path: str = "driftmate.yaml",
        checkout_path: Optional[str] = None,
        renovate_runner: Optional[RenovateRunner] = None,
        trivy_runner: Optional[TrivyRunner] = None,
    ) -> None:
        self._repo = repo
        self._upstream_factory = upstream_factory
        self._manifest_path = manifest_path
        self._checkout_path = checkout_path or os.getcwd()
        self._renovate_runner = renovate_runner or RenovateRunner()
        self._trivy_runner = trivy_runner or TrivyRunner()

    def analyze(
        self, 
        ref: str = "main", 
        scan_cve: bool = False,
        cve_target: Optional[str] = None
    ) -> list[DriftReport]:
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

        # Health check Trivy if requested
        if scan_cve and not self._trivy_runner.check_health():
            raise ManifestError(
                "Trivy CLI is not installed or not healthy. Run 'curl -sfL ... | sh' to install."
            )

        # Note: Trivy image scans may time out (~120s default) for very large base
        # images (e.g., JDK-based eclipse-temurin). If scan_cve is enabled and
        # timeout occurs, the component skips CVE data but drift is still reported.
        reports: list[DriftReport] = []
        
        # Filter dependencies if cve_target is specified
        deps_to_scan = result.dependencies
        if cve_target:
            deps_to_scan = [d for d in deps_to_scan if cve_target in d.package_file]

        for i, dep in enumerate(deps_to_scan):
            if scan_cve:
                image_ref = f"{dep.name}:{dep.current_value}" if dep.datasource == "docker" else None
            else:
                image_ref = None
            
            upstream = dep.new_value if dep.new_value else dep.current_value
            report = compare_versions(dep.name, dep.current_value, upstream)
            report.package_file = dep.package_file
            report.registry_url = dep.registry_url
            
            if scan_cve and dep.datasource == "docker":
                image_ref = f"{dep.name}:{dep.current_value}" if dep.datasource == "docker" else None
                if image_ref:
                    try:
                        vs = self._trivy_runner.scan_image(image_ref)
                        report.vuln_summary = vs
                    except Exception as exc:
                        logger.error("Vulnerability scan failed for %s: %s", dep.name, exc)
                        # Continue with drift report but no CVE data

            # Compute field diff for Helm and Terraform (not Docker)
            if dep.datasource != "docker":
                try:
                    if dep.datasource == "helm" and not dep.registry_url:
                        fd = None
                    else:
                        fd = compute_field_diff(
                            dep_name=dep.name,
                            datasource=dep.datasource,
                            current_value=dep.current_value,
                            new_value=dep.new_value,
                            package_file=dep.package_file,
                            chart_repo=dep.registry_url or "",
                        )
                    if fd is not None:
                        report.field_diff = fd
                except Exception as exc:
                    logger.debug("Field diff failed for %s: %s", dep.name, exc)

            if dep.package_file.endswith(".tf") or dep.datasource == "terraform-module":
                if report.is_drifted:
                    if "~>" in dep.current_value or ">=" in dep.current_value:
                        report.recommendation = f"Range constraint update available: {dep.current_value} -> {dep.new_value}. " + report.recommendation
                    report.recommendation += " (Terraform module bump: manual update required)"
            
            reports.append(report)

        return reports


def compare_versions(component: str, declared: str, upstream: str) -> DriftReport:
    # Handle range constraints: e.g. ~> 7.0 -> ~> 8.0
    if declared.startswith("~>") or declared.startswith(">="):
        is_range_drift = declared != upstream
        return DriftReport(
            component=component,
            declared_version=declared,
            upstream_version=upstream,
            is_drifted=is_range_drift,
            severity=Severity.LOW.value if is_range_drift else Severity.NONE.value,
            recommendation=f"Update constraint from {declared} to {upstream}." if is_range_drift else "",
        )

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
