"""Regression coverage for the public video profiling helper import path."""

import subprocess
import sys
from pathlib import Path


def test_root_collection_loads_the_soak_helper_package():
    """The root collector must reach the soak test without a tools collision."""
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '--collect-only', '-q',
         '--ignore=tests/tools/test_profile_video_import.py'],
        cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert ('tests/integration/test_worker_soak.py::'
            'test_ten_generated_vfr_cycles_leave_no_worker_or_session'
            in result.stdout)
