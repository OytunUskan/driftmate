
from driftmate.core.services.drift_analyzer import (
    Severity,
    compare_versions,
)


class TestCompareVersions:
    def test_equal_versions_have_no_drift(self):
        report = compare_versions("foo", "1.2.3", "1.2.3")
        assert report.is_drifted is False
        assert report.severity == Severity.NONE.value

    def test_major_bump_is_critical(self):
        report = compare_versions("foo", "1.9.5", "2.0.0")
        assert report.is_drifted is True
        assert report.severity == Severity.CRITICAL.value

    def test_minor_bump_is_high(self):
        report = compare_versions("foo", "1.9.5", "1.10.0")
        assert report.is_drifted is True
        assert report.severity == Severity.HIGH.value

    def test_patch_bump_is_medium(self):
        report = compare_versions("foo", "1.2.3", "1.2.4")
        assert report.is_drifted is True
        assert report.severity == Severity.MEDIUM.value

    def test_pinned_ahead_is_low(self):
        report = compare_versions("foo", "2.0.0", "1.0.0")
        assert report.is_drifted is True
        assert report.severity == Severity.LOW.value

    def test_v_prefix_is_stripped(self):
        report = compare_versions("foo", "v1.0.0", "v1.1.0")
        assert report.severity == Severity.HIGH.value

    def test_unparseable_upstream_is_flagged(self):
        report = compare_versions("foo", "1.2.3", "not-a-version")
        assert report.is_drifted is False
        assert report.severity == Severity.NONE.value
        assert report.recommendation == "upstream version unparseable: not-a-version"

    def test_unparseable_declared_is_flagged(self):
        report = compare_versions("foo", "garbage", "1.2.3")
        assert report.recommendation == "declared version unparseable: garbage"
