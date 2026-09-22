"""Trivy CLI execution and vulnerability report parsing."""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TrivyError(Exception):
    """Raised when Trivy execution fails."""


@dataclass
class VulnItem:
    vulnerability_id: str
    severity: str
    pkg_name: str
    installed_version: str
    fixed_version: str


@dataclass
class VulnSummary:
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    unknown: int = 0
    vulnerabilities: list[VulnItem] = field(default_factory=list)


class TrivyRunner:
    def __init__(self, binary_path: Optional[str] = None) -> None:
        self._binary = binary_path or shutil.which("trivy")

    def check_health(self) -> bool:
        """Verify Trivy is installed and functional."""
        if not self._binary:
            return False
        try:
            subprocess.run(
                [self._binary, "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def scan_image(self, image_ref: str) -> VulnSummary:
        """Scan a Docker image ref for vulnerabilities using Trivy JSON output."""
        if not self._binary:
            raise TrivyError(
                "Trivy CLI not found. Please install it (e.g. https://aquasecurity.github.io/trivy/)."
            )

        cmd = [self._binary, "image", image_ref, "--format", "json", "--scanners", "vuln"]
        logger.debug("Executing Trivy: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TrivyError(f"Trivy scan timed out for image {image_ref}") from exc
        except subprocess.SubprocessError as exc:
            raise TrivyError(f"Trivy execution failed: {exc}") from exc

        if result.returncode != 0:
            logger.error("Trivy stderr: %s", result.stderr)
            raise TrivyError(f"Trivy failed with exit code {result.returncode}")

        return self._parse_trivy_output(result.stdout)

    def _parse_trivy_output(self, output: str) -> VulnSummary:
        summary = VulnSummary()
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Trivy JSON output: %s", exc)
            return summary

        results = data.get("Results", [])
        if not results:
            return summary

        all_vulns: list[VulnItem] = []
        for res in results:
            vulns = res.get("Vulnerabilities", [])
            if not vulns:
                continue
            for v in vulns:
                sev = v.get("Severity", "UNKNOWN").upper()
                if sev == "CRITICAL":
                    summary.critical += 1
                elif sev == "HIGH":
                    summary.high += 1
                elif sev == "MEDIUM":
                    summary.medium += 1
                elif sev == "LOW":
                    summary.low += 1
                else:
                    summary.unknown += 1

                all_vulns.append(
                    VulnItem(
                        vulnerability_id=v.get("VulnerabilityID", "UNKNOWN"),
                        severity=sev,
                        pkg_name=v.get("PkgName", "UNKNOWN"),
                        installed_version=v.get("InstalledVersion", ""),
                        fixed_version=v.get("FixedVersion", ""),
                    )
                )

        summary.vulnerabilities = all_vulns
        return summary
