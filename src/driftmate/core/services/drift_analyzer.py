"""Vendor-agnostic drift detection.

Compares component versions declared in a target repository against the
versions declared in their upstream GitHub repositories (Option A).
There is no live cluster connection; cluster-state fetching is out of scope.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import yaml

from driftmate.core.interfaces.repo_provider import RepoProvider
from driftmate.core.models.repo import Content


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


@dataclass
class Manifest:
    components: list[ComponentSpec] = field(default_factory=list)


class ManifestError(Exception):
    """Raised when manifest file cannot be fetched or parsed."""


class ManifestNotFoundError(ManifestError):
    """Raised when manifest file is not found at the specified ref."""


class DriftAnalyzer:
    def __init__(
        self,
        repo: RepoProvider,
        upstream_factory: Callable[[str, str], RepoProvider],
        manifest_path: str = "driftmate.yaml",
    ) -> None:
        self._repo = repo
        self._upstream_factory = upstream_factory
        self._manifest_path = manifest_path

    def analyze(self, ref: str) -> list[DriftReport]:
        try:
            manifest_content = self._repo.getFile(self._manifest_path, ref)
        except Exception as exc:
            raise ManifestNotFoundError(
                f"Manifest '{self._manifest_path}' not found at ref '{ref}': {exc}"
            ) from exc
        try:
            manifest = parse_manifest(manifest_content.content)
        except Exception as exc:
            raise ManifestError(
                f"Failed to parse manifest '{self._manifest_path}': {exc}"
            ) from exc
        return [self._analyze_component(spec) for spec in manifest.components]

    def _analyze_component(self, spec: ComponentSpec) -> DriftReport:
        if spec.error:
            return DriftReport(
                component=spec.name,
                declared_version=spec.version,
                upstream_version="unknown",
                is_drifted=False,
                severity=Severity.NONE.value,
                recommendation=spec.error,
            )

        try:
            upstream_provider = self._upstream_factory(
                spec.upstream_owner, spec.upstream_repo
            )
            upstream_content = upstream_provider.getFile(
                spec.upstream_path, spec.upstream_ref
            )
        except Exception as exc:
            return DriftReport(
                component=spec.name,
                declared_version=spec.version,
                upstream_version="unknown",
                is_drifted=False,
                severity=Severity.NONE.value,
                recommendation=f"Unable to fetch upstream version: {exc}",
            )

        try:
            upstream_version = extract_version(upstream_content, spec.version_key)
        except ValueError as exc:
            return DriftReport(
                component=spec.name,
                declared_version=spec.version,
                upstream_version="unknown",
                is_drifted=False,
                severity=Severity.NONE.value,
                recommendation=str(exc),
            )

        if not upstream_version:
            return DriftReport(
                component=spec.name,
                declared_version=spec.version,
                upstream_version="unknown",
                is_drifted=False,
                severity=Severity.NONE.value,
                recommendation="Unable to determine upstream version.",
            )

        return compare_versions(spec.name, spec.version, upstream_version)


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
