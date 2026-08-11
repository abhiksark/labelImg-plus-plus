"""Build and install a real external entry-point plugin wheel."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap


def _run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def _stage_base_project(root, destination):
    destination.mkdir()
    for name in (
            "pyproject.toml", "setup.cfg", "MANIFEST.in", "README.rst",
            "LICENSE", "labelImgPlusPlus.py", "resources.qrc"):
        shutil.copy2(root / name, destination / name)
    for name in ("libs", "labelimgplusplus", "resources", "data"):
        shutil.copytree(
            root / name, destination / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


def test_packaged_plugin_lifecycle_and_removal(tmp_path):
    root = Path(__file__).resolve().parents[2]
    base_source = tmp_path / "base-source"
    fixture_source = tmp_path / "fixture-source"
    wheelhouse = tmp_path / "wheelhouse"
    environment = tmp_path / "environment"
    wheelhouse.mkdir()
    _stage_base_project(root, base_source)
    shutil.copytree(
        root / "tests" / "fixtures" / "plugin_distribution",
        fixture_source,
    )

    for source in (base_source, fixture_source):
        _run([
            sys.executable, "-m", "pip", "wheel", "--no-deps",
            "--wheel-dir", str(wheelhouse), str(source),
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    base_wheel, = wheelhouse.glob("labelimgplusplus-*.whl")
    fixture_wheel, = wheelhouse.glob("labelimgpp_test_plugin-*.whl")
    _run([sys.executable, "-m", "venv", "--system-site-packages", str(environment)])
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _run([
        str(python), "-m", "pip", "install", "--no-deps",
        "--force-reinstall", str(base_wheel), str(fixture_wheel),
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    settings_path = tmp_path / "settings.json"
    lifecycle = tmp_path / "lifecycle.py"
    lifecycle.write_text(textwrap.dedent("""
        import os
        import sys
        from PyQt5.QtWidgets import QApplication
        import labelImgPlusPlus
        from libs.core.plugin_discovery import discover_plugins
        from libs.core.plugin_manager import PluginManager, PluginState
        from libs.core.settings import Settings
        from libs.core.task_coordinator import TaskCoordinator

        assert 'av' not in sys.modules
        assert 'cv2' not in sys.modules
        assert 'numpy' not in sys.modules
        assert 'torch' not in sys.modules
        assert 'torchvision' not in sys.modules
        assert 'sam2' not in sys.modules
        candidates = discover_plugins()
        candidate = next(item for item in candidates
                         if item.id == 'org.labelimgpp.fixture')
        assert candidate.distribution == 'labelimgpp-test-plugin'
        assert 'labelimgpp_fixture_plugin' not in sys.modules

        app = QApplication.instance() or QApplication([])
        settings = Settings()
        settings.path = os.environ['PLUGIN_TEST_SETTINGS']
        settings.data = {'plugins': {
            'enabled': ['org.labelimgpp.fixture'], 'config': {}}}
        coordinator = TaskCoordinator(logical_cpus=1)
        manager = PluginManager(settings, coordinator, candidates=candidates)
        manager.activate_enabled()
        record = manager.record_for('org.labelimgpp.fixture')
        assert record.state == PluginState.ACTIVE
        assert manager.invoke_command(
            'plugin.org.labelimgpp.fixture.execute')
        import labelimgpp_fixture_plugin as fixture
        assert fixture.EXECUTIONS == 1
        assert settings.get('plugins')['config'][record.id]['activated'] is True
        manager.set_enabled(record.id, False)
        assert record.state == PluginState.ACTIVE
        assert record.enabled is False
        manager.shutdown()
        assert fixture.DEACTIVATIONS == 1
        coordinator.shutdown()
    """), encoding="utf-8")
    process_environment = dict(os.environ)
    process_environment.pop("PYTHONPATH", None)
    process_environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "PLUGIN_TEST_SETTINGS": str(settings_path),
    })
    _run([str(python), str(lifecycle)], cwd=tmp_path, env=process_environment)

    _run([
        str(python), "-m", "pip", "uninstall", "-y",
        "labelimgpp-test-plugin",
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    removed = tmp_path / "removed.py"
    removed.write_text(textwrap.dedent("""
        import os
        from PyQt5.QtWidgets import QApplication
        from libs.core.plugin_discovery import discover_plugins
        from libs.core.plugin_manager import PluginManager, PluginState
        from libs.core.settings import Settings
        from libs.core.task_coordinator import TaskCoordinator

        assert all(item.id != 'org.labelimgpp.fixture'
                   for item in discover_plugins())
        app = QApplication.instance() or QApplication([])
        settings = Settings()
        settings.path = os.environ['PLUGIN_TEST_SETTINGS']
        assert settings.load()
        coordinator = TaskCoordinator(logical_cpus=1)
        manager = PluginManager(settings, coordinator, candidates=[])
        record = manager.record_for('org.labelimgpp.fixture')
        assert record.state == PluginState.UNAVAILABLE
        assert settings.get('plugins')['config'][record.id]['activated'] is True
        manager.shutdown()
        coordinator.shutdown()
    """), encoding="utf-8")
    _run([str(python), str(removed)], cwd=tmp_path, env=process_environment)
