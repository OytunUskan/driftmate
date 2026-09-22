import pytest
import shutil
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch


from driftmate.app.init_cmd import _check_renovate

@patch("shutil.which")
def test_check_renovate_no_npm(mock_which):
    mock_which.return_value = None
    with pytest.raises(SystemExit) as e:
        _check_renovate()
    assert e.value.code == 1

@patch("driftmate.app.init_cmd.RenovateRunner")
@patch("shutil.which")
def test_check_renovate_already_installed(mock_which, mock_runner_cls):
    mock_which.return_value = "/usr/bin/npm"
    mock_runner = MagicMock()
    mock_runner.check_health.return_value = True
    mock_runner_cls.return_value = mock_runner
    
    _check_renovate()
    assert mock_runner.check_health.called

@patch("driftmate.app.init_cmd.RenovateRunner")
@patch("shutil.which")
@patch("subprocess.Popen")
def test_check_renovate_install_success(mock_popen, mock_which, mock_runner_cls):
    mock_which.return_value = "/usr/bin/npm"
    mock_runner = MagicMock()
    mock_runner.check_health.side_effect = [False, True] # First check: False, second check: True
    mock_runner_cls.return_value = mock_runner
    
    mock_process = MagicMock()
    mock_process.poll.side_effect = [None, None, 0] # Busy, busy, finished
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    _check_renovate()
    assert mock_popen.called
    assert mock_runner.check_health.call_count == 2

@patch("driftmate.app.init_cmd.RenovateRunner")
@patch("shutil.which")
@patch("subprocess.Popen")
def test_check_renovate_install_failure(mock_popen, mock_which, mock_runner_cls):
    mock_which.return_value = "/usr/bin/npm"
    mock_runner = MagicMock()
    mock_runner.check_health.return_value = False
    mock_runner_cls.return_value = mock_runner
    
    mock_process = MagicMock()
    mock_process.poll.return_value = 0
    mock_process.returncode = 1
    mock_popen.return_value = mock_process
    
    with pytest.raises(SystemExit) as e:
        _check_renovate()
    assert e.value.code == 1
