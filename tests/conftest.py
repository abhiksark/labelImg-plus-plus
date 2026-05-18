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


def pytest_sessionfinish(session, exitstatus):
    """Close every top-level widget and quit QApplication before exit."""
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except Exception:
            pass

    app.processEvents()
    app.processEvents()
    app.quit()
    gc.collect()
