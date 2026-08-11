import json
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import subprocess
import sys


_PROFILE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools" / "performance" / "profile_plugins.py")
_SPEC = spec_from_file_location("labelimgpp_plugin_profile", _PROFILE_PATH)
_PROFILE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PROFILE)


def test_plugin_performance_and_teardown_gates():
    result = _PROFILE.profile_plugins(runs=5)
    _PROFILE.assert_budgets(result)


def test_plugin_profiler_runs_by_path_outside_repository(tmp_path):
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [sys.executable, str(_PROFILE_PATH), "--runs", "1"],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["runs"] == 1
    assert result["teardown_clean"] is True
