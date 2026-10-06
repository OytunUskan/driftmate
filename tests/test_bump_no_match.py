"""bump_package_file must fail loudly when the component is not in the file."""

import pytest

from driftmate.core.services.remediation_orchestrator import bump_package_file


def test_dockerfile_without_component_raises():
    content = "FROM python:3.11-slim\nRUN echo hi\n"
    with pytest.raises(ValueError, match="nginx"):
        bump_package_file(content, "Dockerfile", "nginx", "1.27")


def test_chart_without_dependency_raises():
    content = (
        "apiVersion: v2\nname: app\nversion: 0.1.0\n"
        "dependencies:\n  - name: redis\n    version: \"17.0.0\"\n"
        "    repository: https://charts.bitnami.com/bitnami\n"
    )
    with pytest.raises(ValueError, match="nginx"):
        bump_package_file(content, "Chart.yaml", "nginx", "15.14.2")


def test_dockerfile_already_at_target_raises():
    content = "FROM nginx:1.27\n"
    with pytest.raises(ValueError):
        bump_package_file(content, "Dockerfile", "nginx", "1.27")


def test_matching_component_still_bumps():
    updated = bump_package_file("FROM nginx:1.25\n", "Dockerfile", "nginx", "1.27")
    assert "FROM nginx:1.27" in updated
