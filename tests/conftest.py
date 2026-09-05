# tests/conftest.py
"""Pytest session hooks shared across the suite.

The session-finish hook forces an explicit QApplication teardown so that
coverage's atexit handler does not race with delayed QObject destructors.
Under QT_QPA_PLATFORM=offscreen on GitHub Actions runners, that race
segfaults at interpreter shutdown (exit 139) even though every test passes.
"""

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_TEST_APPLICATION = None


def pytest_sessionstart(session):
    """Keep one strong QApplication reference for the complete test run."""
    del session
    global _TEST_APPLICATION
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        _TEST_APPLICATION = QApplication([])
    else:
        _TEST_APPLICATION = QApplication.instance()
    assert _TEST_APPLICATION is not None


def pytest_sessionfinish(session, exitstatus):
    """Close every top-level widget and quit QApplication before exit."""
    del session, exitstatus
    global _TEST_APPLICATION
    try:
        from PyQt6.QtWidgets import QApplication
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
