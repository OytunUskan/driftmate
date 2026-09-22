import os
from unittest.mock import patch
import pytest

from driftmate.app.scan_cmd import run_scan


def test_scan_command(tmp_path, monkeypatch):
    # Clear environment tokens to verify no tokens are required
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # Create dummy Dockerfile
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM nginx:1.20\n")

    # Mock RenovateRunner to avoid actual CLI execution in unit test, or test actual runner if installed.
    # Since scan relies on RenovateRunner, mocking run_lookup is best for pure unit test.
    with patch("driftmate.core.services.renovate_runner.RenovateRunner.check_health", return_value=True):
        with patch("driftmate.core.services.renovate_runner.RenovateRunner.run_lookup") as mock_lookup:
            from driftmate.core.services.renovate_runner import RenovateDependency, RenovateResult
            mock_lookup.return_value = RenovateResult(
                dependencies=[
                    RenovateDependency(
                        name="nginx",
                        package_name="nginx",
                        current_value="1.20",
                        datasource="docker",
                        package_file="Dockerfile",
                        new_value="1.31",
                        update_type="minor",
                    )
                ]
            )

            run_scan(path=str(tmp_path))

    report_file = tmp_path / "driftmate-report.md"
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "# Driftmate Report" in content
    assert "nginx" in content
    assert "1.20" in content
    assert "1.31" in content
