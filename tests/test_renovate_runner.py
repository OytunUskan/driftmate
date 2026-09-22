from unittest.mock import MagicMock, patch

import pytest

from driftmate.core.services.renovate_runner import RenovateError, RenovateRunner


def test_parse_renovate_output_success():
    runner = RenovateRunner()
    # Mocking real Renovate debug output format
    output = """
DEBUG: some noise
DEBUG: packageFiles with updates (repository=local, baseBranch=)
       "config": {
         "dockerfile": [
           {
             "deps": [
               {
                 "depName": "nginx",
                 "currentValue": "1.27",
                 "updates": [{"newValue": "1.31", "updateType": "minor"}]
               }
             ],
             "packageFile": "Dockerfile"
           }
         ],
         "helmv3": [
           {
             "deps": [
               {
                 "depName": "prometheus",
                 "currentValue": "15.0.0",
                 "updates": [{"newValue": "15.1.0", "updateType": "minor"}]
               }
             ],
             "packageFile": "Chart.yaml"
           }
         ]
       }
DEBUG: more noise
"""
    result = runner._parse_renovate_output(output)
    assert len(result.dependencies) == 2
    
    nginx = next(d for d in result.dependencies if d.name == "nginx")
    assert nginx.current_value == "1.27"
    assert nginx.new_value == "1.31"
    assert nginx.package_file == "Dockerfile"
    
    prom = next(d for d in result.dependencies if d.name == "prometheus")
    assert prom.current_value == "15.0.0"
    assert prom.new_value == "15.1.0"
    assert prom.package_file == "Chart.yaml"

@patch("subprocess.run")
def test_run_lookup_failure(mock_run):
    mock_run.returncode = 1
    mock_run.stderr = "Fatal error"
    
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Fatal error"
    mock_run.return_value = mock_result
    
    with pytest.raises(RenovateError, match="Renovate failed with exit code 1"):
        runner.run_lookup(".")

@patch("subprocess.run")
def test_check_health_success(mock_run):
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    mock_run.return_value = MagicMock(returncode=0)
    assert runner.check_health() is True

@patch("subprocess.run")
def test_concurrency_lock(mock_run):
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    mock_run.return_value = MagicMock(returncode=0, stdout="packageFiles with updates", stderr="")
    
    # Manually acquire lock to simulate concurrent run
    RenovateRunner._lock.acquire()
    try:
        with pytest.raises(RenovateError, match="An analysis is already in progress"):
            runner.run_lookup(".")
    finally:
        RenovateRunner._lock.release()
