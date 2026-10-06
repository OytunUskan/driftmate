"""US-003: timeout error message must state the configured timeout.

subprocess.run is called with timeout=180 but RenovateError said
"timed out after 120s".
"""

import subprocess
from unittest.mock import patch

import pytest

from driftmate.core.services.renovate_runner import RenovateError, RenovateRunner


@patch("subprocess.run")
def test_timeout_error_message_matches_configured_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["renovate"], timeout=180)
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    with pytest.raises(RenovateError) as exc_info:
        runner.run_lookup(".")
    assert mock_run.call_args.kwargs["timeout"] == 180, (
        "subprocess.run must still be called with the configured 180s timeout"
    )
    message = str(exc_info.value)
    assert "180" in message, (
        f"timeout message must state the configured 180s timeout, got: {message!r}"
    )
    assert "120" not in message, f"stale 120s in timeout message: {message!r}"
