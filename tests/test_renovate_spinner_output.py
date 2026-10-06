"""US-002: spinner renders only on a TTY; non-TTY stdout stays silent.

Non-TTY runs (Docker/log pipelines) used to receive one
`Discovering dependencies...` line on stdout per second, for the entire
life of the process. The TTY case is a protective test: the spinner must
keep rendering while Renovate runs.
"""

import time
from unittest.mock import MagicMock, patch

from driftmate.core.services.renovate_runner import RenovateRunner


class _FakeStdout:
    def __init__(self, tty: bool) -> None:
        self._tty = tty
        self.writes: list[str] = []

    def isatty(self) -> bool:
        return self._tty

    def write(self, s: str) -> int:
        self.writes.append(s)
        return len(s)

    def flush(self) -> None:
        return None


def _slow_subprocess(*_args, **_kwargs):
    # Keep run_lookup busy long enough for the 1s spinner to tick.
    time.sleep(1.5)
    return MagicMock(returncode=0, stdout="", stderr="")


def test_non_tty_stdout_receives_no_spinner_output():
    fake = _FakeStdout(tty=False)
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    with patch("subprocess.run", side_effect=_slow_subprocess), patch("sys.stdout", fake):
        runner.run_lookup(".")
    assert fake.writes == [], (
        f"non-TTY stdout must stay silent, got {len(fake.writes)} write(s): "
        f"{fake.writes[:3]!r}"
    )


def test_tty_stdout_still_renders_spinner():
    fake = _FakeStdout(tty=True)
    runner = RenovateRunner(binary_path="/usr/bin/renovate")
    with patch("subprocess.run", side_effect=_slow_subprocess), patch("sys.stdout", fake):
        runner.run_lookup(".")
    assert any("Discovering dependencies" in w for w in fake.writes), (
        "spinner must still render on stdout while Renovate runs when stdout is a TTY"
    )
