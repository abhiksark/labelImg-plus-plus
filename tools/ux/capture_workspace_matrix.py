#!/usr/bin/env python
"""Capture the deterministic continuous-image workspace review matrix."""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '0')
os.environ.setdefault('QT_SCALE_FACTOR', '1')

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from PyQt5.QtCore import QRect, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QImage, QPainter, QPen  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from labelImgPlusPlus import get_main_app  # noqa: E402
from libs.formats.labelFile import LabelFileFormat  # noqa: E402
from libs.utils.styles import Theme  # noqa: E402


SIZES = ((800, 600), (960, 640), (1366, 768), (1440, 900))
THEMES = ('light', 'dark')
SCENARIO_ORDER = (
    'empty-workspace',
    'first-image-fit',
    'two-rectangles',
    'inspector-open',
    'inspector-closed',
    'saving',
    'saved',
    'save-failed',
)


def _wait(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    return False


def _settle():
    QApplication.processEvents()
    QTest.qWait(10)
    QApplication.processEvents()


def _set_capture_status(window, message):
    window.statusBar().showMessage(message)
    QApplication.processEvents()


def _context(window):
    context = getattr(window, '_ux_capture_context', None)
    if context is None:
        raise RuntimeError('image scenarios require a capture context')
    return context


def _empty_workspace(window):
    window.dirty = False
    window.close_file()
    window.recent_files = []
    window.workspace_pages.empty_page.set_recent_paths(())
    window.workspace_shell.close_inspector()
    _settle()
    _set_capture_status(window, 'Ready to open an image dataset')


def _first_image_fit(window):
    context = _context(window)
    if window.file_path != context.image_path:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        assert window.import_dir_images(context.dataset_dir)
    window.workspace_shell.close_inspector()
    window.set_fit_window()
    assert _wait(lambda: window.canvas.pixmap is not None)
    _settle()
    _set_capture_status(window, 'First image fitted to the canvas')


def _two_rectangles(window):
    _first_image_fit(window)
    if len(window.canvas.shapes) == 0:
        window._active_class_selected('vehicle')
        window.activate_box_tool()
        window.canvas.commit_rectangle((70, 60, 260, 230))
        QApplication.processEvents()
        window.canvas.commit_rectangle((330, 140, 560, 390))
        QApplication.processEvents()
    assert len(window.canvas.shapes) == 2
    window._active_class_selected('vehicle')
    window.activate_box_tool()
    assert _wait(lambda: window.continuous_save.state == 'saved')
    _settle()
    _set_capture_status(window, 'Two rectangles committed')


def _inspector_open(window):
    _two_rectangles(window)
    window.workspace_shell.open_inspector()
    _settle()
    _set_capture_status(window, 'Inspector open')


def _inspector_closed(window):
    _two_rectangles(window)
    window.workspace_shell.close_inspector()
    _settle()
    _set_capture_status(window, 'Inspector closed')


def _saving(window):
    _inspector_closed(window)
    coordinator = window.continuous_save
    coordinator.set_enabled(False)
    coordinator.mark_dirty(window._document_revision + 1)
    assert coordinator.state == 'pending'
    _settle()
    _set_capture_status(window, 'Saving annotation')


def _saved(window):
    coordinator = window.continuous_save
    coordinator.set_enabled(True)
    assert _wait(lambda: coordinator.state == 'saved')
    _settle()
    _set_capture_status(window, 'Annotation saved')


def _save_failed(window):
    _two_rectangles(window)
    coordinator = window.continuous_save
    coordinator.set_enabled(False)
    coordinator.reset(
        window._continuous_document_key(), window._dataset_generation,
        window._document_revision)
    coordinator.mark_dirty(window._document_revision + 1)
    coordinator.set_enabled(True)
    ticket = coordinator._in_flight
    assert ticket is not None
    coordinator.fail(ticket, 'Deterministic screenshot failure')
    assert coordinator.state == 'failed'
    _settle()
    _set_capture_status(window, 'Save failed; retry is available')


IMAGE_SCENARIOS = {
    'empty-workspace': _empty_workspace,
    'first-image-fit': _first_image_fit,
    'two-rectangles': _two_rectangles,
    'inspector-open': _inspector_open,
    'inspector-closed': _inspector_closed,
    'saving': _saving,
    'saved': _saved,
    'save-failed': _save_failed,
}


def capture_scenario(window, scenario, size, theme, output_dir):
    """Apply one named state and save its full-window PNG."""
    window.resize(*size)
    selected_theme = Theme.DARK if theme == 'dark' else Theme.LIGHT
    window._current_theme = selected_theme
    window._apply_theme(selected_theme)
    IMAGE_SCENARIOS[scenario](window)
    QApplication.processEvents()
    filename = '%s-%s-%sx%s.png' % (
        scenario, theme, size[0], size[1])
    output_dir = os.fspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    assert window.grab().save(path, 'PNG')
    return path


def _write_sample_image(path):
    image = QImage(640, 480, QImage.Format_RGB32)
    image.fill(QColor('#dce6ee'))
    painter = QPainter(image)
    painter.fillRect(QRect(0, 300, 640, 180), QColor('#c5d6b0'))
    painter.fillRect(QRect(0, 0, 640, 90), QColor('#b9d7ea'))
    painter.setPen(QPen(QColor('#8aa1b2'), 2))
    for x in range(0, 641, 80):
        painter.drawLine(x, 0, x, 480)
    for y in range(0, 481, 60):
        painter.drawLine(0, y, 640, y)
    painter.setPen(QPen(QColor('#536878'), 4))
    painter.drawRect(QRect(70, 60, 190, 170))
    painter.drawRect(QRect(330, 140, 230, 250))
    painter.end()
    assert image.save(str(path), 'PNG')


def _capture_matrix(output_dir):
    captured = []
    with tempfile.TemporaryDirectory(prefix='labelimgpp-ux-matrix-') as root:
        root_path = Path(root)
        for size in SIZES:
            for theme in THEMES:
                dataset_dir = root_path / (
                    '%s-%sx%s' % (theme, size[0], size[1]))
                dataset_dir.mkdir()
                image_path = dataset_dir / 'continuous-sample.png'
                _write_sample_image(image_path)
                _app, window = get_main_app()
                try:
                    window._ux_capture_context = SimpleNamespace(
                        dataset_dir=str(dataset_dir),
                        image_path=str(image_path))
                    window.resize(*size)
                    window.show()
                    _settle()
                    for scenario in SCENARIO_ORDER:
                        path = capture_scenario(
                            window, scenario, size, theme, output_dir)
                        screenshot = QImage(path)
                        assert not screenshot.isNull()
                        assert screenshot.size().width() == size[0]
                        assert screenshot.size().height() == size[1]
                        assert os.path.getsize(path) > 0
                        captured.append(path)
                finally:
                    window.continuous_save.set_enabled(False)
                    window.dirty = False
                    window.close()
                    QApplication.processEvents()
    expected = len(SIZES) * len(THEMES) * len(SCENARIO_ORDER)
    assert len(captured) == expected
    return captured


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output-dir',
        default=str(
            REPOSITORY_ROOT / 'docs' / 'screenshots' /
            'continuous-workflow-2026-08-24'))
    args = parser.parse_args(argv)
    paths = _capture_matrix(args.output_dir)
    for path in paths:
        print(os.path.relpath(path, REPOSITORY_ROOT))
    print('Captured %d deterministic PNG files.' % len(paths))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
