from unittest.mock import MagicMock
import pytest

from driftmate.core.services.drift_analyzer import DriftAnalyzer, Severity
from driftmate.core.services.renovate_runner import RenovateDependency, RenovateResult
from driftmate.core.services.remediation_orchestrator import bump_package_file


def test_drift_analyzer_with_mocked_renovate():
    mock_runner = MagicMock()
    mock_runner.check_health.return_value = True
    mock_runner.run_lookup.return_value = RenovateResult(
        dependencies=[
            RenovateDependency(
                name="nginx",
                package_name="nginx",
                current_value="1.27",
                datasource="docker",
                package_file="Dockerfile",
                new_value="1.31",
                update_type="minor",
            ),
            RenovateDependency(
                name="nginx-chart",
                package_name="nginx",
                current_value="15.0.0",
                datasource="helm",
                package_file="Chart.yaml",
                new_value="15.14.2",
                update_type="minor",
            ),
            RenovateDependency(
                name="vpc",
                package_name="terraform-aws-modules/vpc/aws",
                current_value="3.0.0",
                datasource="terraform-module",
                package_file="main.tf",
                new_value="3.19.0",
                update_type="minor",
            ),
        ]
    )

    analyzer = DriftAnalyzer(checkout_path=".", renovate_runner=mock_runner)
    reports = analyzer.analyze("main")

    assert len(reports) == 3

    docker_report = next(r for r in reports if r.package_file == "Dockerfile")
    assert docker_report.component == "nginx"
    assert docker_report.is_drifted is True
    assert docker_report.declared_version == "1.27"
    assert docker_report.upstream_version == "1.31"
    assert docker_report.severity == Severity.HIGH.value

    helm_report = next(r for r in reports if r.package_file == "Chart.yaml")
    assert helm_report.is_drifted is True
    assert helm_report.declared_version == "15.0.0"
    assert helm_report.upstream_version == "15.14.2"

    tf_report = next(r for r in reports if r.package_file == "main.tf")
    assert tf_report.is_drifted is True
    assert "Terraform module bump: manual update required" in tf_report.recommendation


def test_bump_package_file_dockerfile():
    dockerfile_content = "FROM nginx:1.20\nCOPY . /usr/share/nginx/html\n"
    updated = bump_package_file(dockerfile_content, "Dockerfile", "nginx", "1.27")
    assert "FROM nginx:1.27\n" in updated
    assert "COPY . /usr/share/nginx/html\n" in updated


def test_bump_package_file_multi_stage_dockerfile():
    dockerfile_content = (
        "FROM golang:1.20 AS builder\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN go build -o bin\n"
        "\n"
        "FROM nginx:1.27\n"
        "COPY --from=builder /app/bin /usr/share/nginx/html\n"
    )
    # Bump only nginx, leave golang alone
    updated = bump_package_file(dockerfile_content, "Dockerfile", "nginx", "1.31")
    assert "FROM golang:1.20 AS builder\n" in updated
    assert "FROM nginx:1.31\n" in updated
    assert "COPY --from=builder /app/bin /usr/share/nginx/html\n" in updated

    # Bump only golang, leave nginx alone
    updated_go = bump_package_file(dockerfile_content, "Dockerfile", "golang", "1.22")
    assert "FROM golang:1.22 AS builder\n" in updated_go
    assert "FROM nginx:1.27\n" in updated_go


def test_bump_package_file_chart_yaml():
    chart_content = (
        "apiVersion: v2\n"
        "name: drift-test\n"
        "version: 0.1.0\n"
        "dependencies:\n"
        "  - name: nginx\n"
        "    version: \"15.0.0\"\n"
        "    repository: \"https://charts.bitnami.com/bitnami\"\n"
    )
    updated = bump_package_file(chart_content, "Chart.yaml", "nginx", "15.14.2")
    assert 'version: "15.14.2"' in updated or "version: '15.14.2'" in updated or "15.14.2" in updated
