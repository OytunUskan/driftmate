"""Standalone scan command ('driftmate scan')."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from driftmate.core.services.drift_analyzer import DriftAnalyzer, ManifestError
from driftmate.core.services.remediation_orchestrator import format_report
from driftmate.core.services.field_diff import compute_field_diff

logger = logging.getLogger(__name__)


def _cve_short(vs) -> str:
    """Short CVE summary for table: '0C/2H/6M/12L' or '-'."""
    if vs is None:
        return "-"
    return f"{vs.critical}C/{vs.high}H/{vs.medium}M/{vs.low}L"


def _field_changes_summary(fd) -> str:
    """Short field diff summary for table."""
    if fd is None:
        return "N/A"
    return fd.summary()


def _build_markdown_table(reports: list) -> str:
    """Build a markdown table from DriftReport list."""
    lines = [
        "| Component | File | Current | Target | Severity | CVEs | Field Changes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        comp = r.component
        file_path = r.package_file or "-"
        current = r.declared_version
        target = r.upstream_version if r.upstream_version != "unknown" else "-"
        severity = r.severity
        cves = _cve_short(r.vuln_summary)
        fields = _field_changes_summary(r.field_diff)
        lines.append(f"| {comp} | {file_path} | {current} | {target} | {severity} | {cves} | {fields} |")
    return "\n".join(lines)


def _build_field_diff_section(reports: list) -> str:
    """Build field diff detail sections for components with diffs."""
    sections = []
    for r in reports:
        if r.field_diff is None or r.field_diff.is_empty():
            continue
        fd = r.field_diff
        lines = [
            f"### {r.component} ({r.package_file}) — Field Changes",
        ]
        if fd.added:
            lines.append(f"- Added: {', '.join(fd.added)}")
        if fd.removed:
            lines.append(f"- Removed: {', '.join(fd.removed)}")
        if fd.type_changed:
            lines.append(f"- Type changed: {', '.join(fd.type_changed)}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) if sections else ""


def run_scan(path: Optional[str] = None, output: Optional[str] = None, scan_cve: bool = False, cve_target: Optional[str] = None) -> None:
    target_path = path or os.getcwd()
    if not os.path.isdir(target_path):
        print(f"Error: Directory not found: {target_path}")
        raise SystemExit(1)

    if scan_cve:
        print("CVE scanning enabled (Trivy) — image scans begin now (progress shown):")

    print(f"Scanning directory: {target_path} ...")
    analyzer = DriftAnalyzer(checkout_path=target_path)

    try:
        reports = analyzer.analyze("main", scan_cve=scan_cve, cve_target=cve_target)
    except ManifestError as exc:
        print(f"Scan failed: {exc}")
        raise SystemExit(1) from exc

    report_text = format_report(reports)
    print("\n" + report_text)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    table = _build_markdown_table(reports)
    field_section = _build_field_diff_section(reports)

    md_content = f"""# Driftmate Report

**Scanned Path:** `{os.path.abspath(target_path)}`  
**Scan Timestamp:** `{timestamp}`  

## Summary

{table}

## Field-Level Changes

{field_section if field_section else "No field-level changes detected for Helm/Terraform components."}

## Text Report

```text
{report_text}
```
"""
    
    # Try to add real field diffs for Helm/Terraform if registry access available
    extra_field_sections = []
    for r in reports:
        if r.package_file and (r.package_file.endswith("Chart.yaml") or r.package_file.endswith(".tf")):
            fd = None
            try:
                chart_repo = getattr(r, "registry_url", None) or ""
                if r.package_file.endswith("Chart.yaml") and not chart_repo:
                    fd = None
                else:
                        fd = compute_field_diff(
                            dep_name=r.component,
                            datasource="helm" if "Chart" in r.package_file else "terraform-module",
                            current_value=r.declared_version,
                            new_value=r.upstream_version,
                            package_file=r.package_file,
                            chart_repo=chart_repo,
                        )
            except Exception:
                fd = None
            if fd is not None and not fd.is_empty():
                extra_field_sections.append(f"### {r.component} ({r.package_file}) — Field Changes\n- Added: {', '.join(fd.added) if fd.added else '-'}\n- Removed: {', '.join(fd.removed) if fd.removed else '-'}\n- Type changed: {', '.join(fd.type_changed) if fd.type_changed else '-'}")
    
    if extra_field_sections:
        md_content += "\n\n## Real Registry Field Differences (from upstream)\n\n" + "\n\n".join(extra_field_sections)

    output_path = output or os.path.join(target_path, "driftmate-report.md")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"\nReport successfully written to: {output_path}")
    except Exception as exc:
        print(f"Error writing report file: {exc}")
        raise SystemExit(1) from exc
