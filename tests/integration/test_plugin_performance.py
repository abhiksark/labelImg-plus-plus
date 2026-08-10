from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_PROFILE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools" / "performance" / "profile_plugins.py")
_SPEC = spec_from_file_location("labelimgpp_plugin_profile", _PROFILE_PATH)
_PROFILE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PROFILE)


def test_plugin_performance_and_teardown_gates():
    result = _PROFILE.profile_plugins(runs=5)
    _PROFILE.assert_budgets(result)
