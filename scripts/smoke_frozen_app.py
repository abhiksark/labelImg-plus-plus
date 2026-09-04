#!/usr/bin/env python3
"""Verify that a frozen labelImg++ artifact survives normal startup."""

import argparse
import os
from pathlib import Path
import subprocess
from typing import Mapping, Optional, Sequence


_SHUTDOWN_TIMEOUT_SECONDS = 3.0


def verify_process_stays_alive(
        command: Sequence[str], seconds: float,
        env: Mapping[str, str]) -> None:
    """Raise if *command* exits before *seconds*; always reap the process."""
    process = subprocess.Popen(
        list(command),
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        output, _ = process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.communicate(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        return

    raise RuntimeError(
        "process exited before %.3f seconds with status %s:\n%s" %
        (seconds, process.returncode, output)
    )


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be greater than zero")
    return seconds


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Require a frozen labelImg++ artifact to stay alive.")
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--seconds", type=_positive_seconds, default=5.0,
        help="minimum startup lifetime (default: 5 seconds)",
    )
    args = parser.parse_args(argv)
    artifact = args.artifact.resolve()
    if not artifact.is_file():
        parser.error("artifact does not exist: %s" % artifact)

    environment = dict(os.environ)
    environment.update({
        "LABELIMGPP_DISABLE_PLUGINS": "1",
        "QT_QPA_PLATFORM": "offscreen",
    })
    verify_process_stays_alive([str(artifact)], args.seconds, environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
