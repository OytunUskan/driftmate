import pytest

from driftmate.core.models.repo import Content
from driftmate.core.services.drift_analyzer import (
    Severity,
    compare_versions,
    extract_version,
    parse_manifest,
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


class TestParseManifest:
    def test_parses_components(self):
        manifest = parse_manifest(
            "components:\n"
            "  - name: ingress-nginx\n"
            "    version: \"1.9.5\"\n"
            "    upstream:\n"
            "      owner: kubernetes\n"
            "      repo: ingress-nginx\n"
            "      path: charts/ingress-nginx/Chart.yaml\n"
            "      version_key: version\n"
        )
        assert len(manifest.components) == 1
        spec = manifest.components[0]
        assert spec.name == "ingress-nginx"
        assert spec.version == "1.9.5"
        assert spec.upstream_owner == "kubernetes"
        assert spec.upstream_ref == "main"
        assert spec.version_key == "version"

    def test_unquoted_version_marks_error_not_raises(self):
        manifest = parse_manifest(
            "components:\n"
            "  - name: foo\n"
            "    version: 1.10\n"
            "    upstream:\n"
            "      owner: a\n"
            "      repo: b\n"
            "      path: c\n"
        )
        assert len(manifest.components) == 1
        assert manifest.components[0].error == "version field must be quoted"

    def test_bad_component_does_not_stop_others(self):
        manifest = parse_manifest(
            "components:\n"
            "  - name: bad\n"
            "    version: 1.10\n"
            "    upstream:\n"
            "      owner: a\n"
            "      repo: b\n"
            "      path: c\n"
            "  - name: good\n"
            "    version: \"1.9.5\"\n"
            "    upstream:\n"
            "      owner: kubernetes\n"
            "      repo: ingress-nginx\n"
            "      path: Chart.yaml\n"
        )
        assert manifest.components[0].error is not None
        assert manifest.components[1].error is None
        assert manifest.components[1].version == "1.9.5"


class TestExtractVersion:
    def test_extract_plain_text(self):
        content = Content(path="VERSION", content="1.2.3\n", sha="x")
        assert extract_version(content, None) == "1.2.3"

    def test_extract_yaml_key(self):
        content = Content(
            path="Chart.yaml", content="version: 1.10.0\nappVersion: 1.9.0\n", sha="x"
        )
        assert extract_version(content, "version") == "1.10.0"

    def test_extract_binary_returns_empty(self):
        content = Content(path="Chart.yaml", content="\x00", sha="x", is_binary=True)
        assert extract_version(content, "version") == ""

    def test_extract_yaml_numeric_version_raises(self):
        content = Content(path="Chart.yaml", content="version: 1.10\n", sha="x")
        with pytest.raises(ValueError):
            extract_version(content, "version")
