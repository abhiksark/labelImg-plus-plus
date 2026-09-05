import os
import sys

import pytest

from scripts.smoke_frozen_app import verify_process_stays_alive


def test_process_surviving_deadline_is_terminated_and_reaped():
    verify_process_stays_alive(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        seconds=0.05,
        env=os.environ,
    )


def test_surviving_process_tree_is_terminated_and_reaped():
    parent = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        "time.sleep(30)"
    )
    verify_process_stays_alive(
        [sys.executable, "-c", parent],
        seconds=0.05,
        env=os.environ,
    )


def test_early_exit_reports_status_and_captured_output():
    with pytest.raises(RuntimeError) as error:
        verify_process_stays_alive(
            [sys.executable, "-c", "print('startup failed'); raise SystemExit(7)"],
            seconds=2,
            env=os.environ,
        )

    message = str(error.value)
    assert "status 7" in message
    assert "startup failed" in message
