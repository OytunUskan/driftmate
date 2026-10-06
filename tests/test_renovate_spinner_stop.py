"""US-001: Renovate spinner thread must terminate when run_lookup returns.

`_progress` in renovate_runner.py is a `while True` loop with no stop/join,
so every analysis leaked a daemon thread that lived for the whole process.
Both the success and the timeout path are covered. Tests run under a fake
TTY so the spinner is guaranteed to be started.
"""

import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from driftmate.core.services.renovate_runner import RenovateError, RenovateRunner


class _FakeStdout:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def isatty(self) -> bool:
        return True

    def write(self, s: str) -> int:
        self.writes.append(s)
        return len(s)

    def flush(self) -> None:
        return None


def _threads_newer_than(before: set[threading.Thread]) -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t not in before]


def test_progress_thread_stops_after_successful_run():
    fake = _FakeStdout()
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    with patch("sys.stdout", fake), patch(
        "subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")
    ):
        before = set(threading.enumerate())
        runner.run_lookup(".")
    leaked = _threads_newer_than(before)
    assert not leaked, (
        "run_lookup returned but progress thread(s) are still alive: "
        + ", ".join(t.name for t in leaked)
    )


def test_progress_thread_stops_after_timeout():
    fake = _FakeStdout()
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    with patch("sys.stdout", fake), patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["renovate"], timeout=180),
    ):
        before = set(threading.enumerate())
        with pytest.raises(RenovateError, match="timed out"):
            runner.run_lookup(".")
    leaked = _threads_newer_than(before)
    assert not leaked, (
        "run_lookup raised RenovateError but progress thread(s) are still alive: "
        + ", ".join(t.name for t in leaked)
    )
