from driftmate.core.services.drift_analyzer import DriftReport
from driftmate.core.services.remediation_orchestrator import format_report


def test_format_report_statuses():
    reports = [
        DriftReport(
            component="comp-ok",
            declared_version="1.0.0",
            upstream_version="1.0.0",
            is_drifted=False,
            severity="NONE",
            recommendation="",
        ),
        DriftReport(
            component="comp-drift",
            declared_version="1.0.0",
            upstream_version="1.1.0",
            is_drifted=True,
            severity="HIGH",
            recommendation="Update comp-drift from 1.0.0 to 1.1.0.",
        ),
        DriftReport(
            component="broken-component",
            declared_version="",
            upstream_version="unknown",
            is_drifted=False,
            severity="NONE",
            recommendation="version field must be quoted",
        ),
    ]

    text = format_report(reports)
    assert "- [OK] comp-ok: 1.0.0 -> 1.0.0" in text
    assert "- [DRIFT] comp-drift: 1.0.0 -> 1.1.0 (HIGH)" in text
    assert "- [ERROR] broken-component: version field must be quoted" in text
