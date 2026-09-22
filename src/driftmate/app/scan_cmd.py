"""Standalone scan command ('driftmate scan')."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from driftmate.core.services.drift_analyzer import DriftAnalyzer, ManifestError
from driftmate.core.services.remediation_orchestrator import format_report

logger = logging.getLogger(__name__)


def run_scan(path: Optional[str] = None, output: Optional[str] = None) -> None:
    target_path = path or os.getcwd()
    if not os.path.isdir(target_path):
        print(f"Error: Directory not found: {target_path}")
        raise SystemExit(1)

    print(f"Scanning directory: {target_path} ...")
    analyzer = DriftAnalyzer(checkout_path=target_path)

    try:
        reports = analyzer.analyze("main")
    except ManifestError as exc:
        print(f"Scan failed: {exc}")
        raise SystemExit(1) from exc

    report_text = format_report(reports)
    print("\n" + report_text)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    md_content = f"""# Driftmate Report

**Scanned Path:** `{os.path.abspath(target_path)}`  
**Scan Timestamp:** `{timestamp}`  

```text
{report_text}
```
"""

    output_path = output or os.path.join(target_path, "driftmate-report.md")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"\nReport successfully written to: {output_path}")
    except Exception as exc:
        print(f"Error writing report file: {exc}")
        raise SystemExit(1) from exc
