# tests/conftest.py
"""Pytest session hooks shared across the suite.

The session-finish hook forces an explicit QApplication teardown so that
coverage's atexit handler does not race with delayed QObject destructors.
Under QT_QPA_PLATFORM=offscreen on GitHub Actions runners, that race
segfaults at interpreter shutdown (exit 139) even though every test passes.
"""

import gc
import hashlib
import os
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_TEST_APPLICATION = None
_SETTINGS_ENV = 'LABELIMGPP_SETTINGS_PATH'
_MISSING = object()
_ORIGINAL_SETTINGS_ENV = _MISSING
_TEST_SETTINGS_DIR = None
_USER_SETTINGS_PATH = os.path.expanduser('~/.labelImgSettings.json')
_USER_SETTINGS_STATE = None


def _file_state(path):
    """Return content and metadata needed to detect a settings-file write."""
    try:
        stat = os.stat(path)
        with open(path, 'rb') as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        return digest, stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


def pytest_configure(config):
    """Route every test Settings instance to one isolated session file."""
    del config
    global _ORIGINAL_SETTINGS_ENV, _TEST_SETTINGS_DIR, _USER_SETTINGS_STATE
    if _TEST_SETTINGS_DIR is not None:
        return
    _ORIGINAL_SETTINGS_ENV = os.environ.get(_SETTINGS_ENV, _MISSING)
    _USER_SETTINGS_STATE = _file_state(_USER_SETTINGS_PATH)
    _TEST_SETTINGS_DIR = tempfile.mkdtemp(
        prefix='labelimgpp-pytest-settings-')
    path = os.path.join(
        _TEST_SETTINGS_DIR, 'session-settings-%s.json' % os.getpid())
    os.environ[_SETTINGS_ENV] = path


def pytest_sessionstart(session):
    """Keep one strong QApplication reference for the complete test run."""
    del session
    global _TEST_APPLICATION
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    if QApplication.instance() is None:
        try:
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        except AttributeError:
            pass
    _TEST_APPLICATION = QApplication.instance() or QApplication([])


def pytest_sessionfinish(session, exitstatus):
    """Close every top-level widget and quit QApplication before exit."""
    del exitstatus
    global _TEST_APPLICATION
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    for widget in list(app.topLevelWidgets()):
        try:
            # A dirty MainWindow pops a modal "discard changes?" dialog from
            # closeEvent, which blocks/segfaults under offscreen teardown.
            # Tests are not real edit sessions, so suppress the prompt.
            if hasattr(widget, 'dirty'):
                widget.dirty = False
            widget.close()
            widget.deleteLater()
        except Exception:
            pass

    app.processEvents()
    app.processEvents()
    app.quit()
    _TEST_APPLICATION = None
    gc.collect()

    if _file_state(_USER_SETTINGS_PATH) != _USER_SETTINGS_STATE:
        reporter = session.config.pluginmanager.getplugin('terminalreporter')
        if reporter is not None:
            reporter.write_sep(
                '!', 'test run modified ~/.labelImgSettings.json')
        session.exitstatus = 1


def pytest_unconfigure(config):
    """Restore the caller environment and remove the isolated settings file."""
    del config
    global _ORIGINAL_SETTINGS_ENV, _TEST_SETTINGS_DIR
    if _ORIGINAL_SETTINGS_ENV is _MISSING:
        os.environ.pop(_SETTINGS_ENV, None)
    else:
        os.environ[_SETTINGS_ENV] = _ORIGINAL_SETTINGS_ENV
    if _TEST_SETTINGS_DIR is not None:
        shutil.rmtree(_TEST_SETTINGS_DIR, ignore_errors=True)
    _ORIGINAL_SETTINGS_ENV = _MISSING
    _TEST_SETTINGS_DIR = None
