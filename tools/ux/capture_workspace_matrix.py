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


try:  # noqa: E402
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QImage, QPixmap
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication
except ImportError:  # noqa: E402
    from PyQt4.QtCore import Qt
    from PyQt4.QtGui import QApplication, QColor, QImage, QPixmap
    from PyQt4.QtTest import QTest

from labelImgPlusPlus import get_main_app  # noqa: E402
from libs.core.annotation_workflow import (  # noqa: E402
    AnnotationTool, PromptPolicy,
)
from libs.core.assist_state import AssistFailureKind, AssistPhase  # noqa: E402
from libs.core.sam_types import SamResult  # noqa: E402
from libs.core.video_types import (  # noqa: E402
    DocumentKind, VideoFingerprint, VideoFrameRef, VideoFrameResult,
    VideoSessionSnapshot,
)
from libs.formats.labelFile import LabelFileFormat  # noqa: E402
from libs.integrations.model_cache import ModelDownloadProgress  # noqa: E402
from libs.integrations.model_manifest import MOBILE_SAM_MANIFEST  # noqa: E402
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
    'video-paused',
    'video-playing',
    'video-invalid-time',
    'video-track-menu',
    'video-propagation-pending',
    'assist-setup',
    'assist-downloading',
    'assist-failure',
    'assist-preview',
    'shutdown-timeout',
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


def _clear_capture_save_state(window):
    held = getattr(window, '_ux_capture_save', None)
    if held is None:
        return
    coordinator = window.continuous_save
    if coordinator._in_flight == held.ticket:
        coordinator.complete(held.ticket)
    elif coordinator.state == 'failed':
        coordinator.reset(
            window._continuous_document_key(), window._dataset_generation,
            window._document_revision)
    coordinator.set_enabled(held.original_enabled)
    del window._ux_capture_save


def _begin_held_save(window):
    _clear_capture_save_state(window)
    coordinator = window.continuous_save
    original_enabled = coordinator.enabled
    coordinator.saveRequested.disconnect(window._dispatch_continuous_save)
    try:
        coordinator.set_enabled(False)
        coordinator.reset(
            window._continuous_document_key(), window._dataset_generation,
            window._document_revision)
        coordinator.mark_dirty(window._document_revision + 1)
        coordinator.set_enabled(True)
        ticket = coordinator._in_flight
        assert coordinator.state == 'saving'
        assert ticket is not None
    finally:
        coordinator.saveRequested.connect(window._dispatch_continuous_save)
    window._ux_capture_save = SimpleNamespace(
        ticket=ticket, original_enabled=original_enabled)
    return ticket


def _empty_workspace(window):
    _clear_capture_save_state(window)
    window.dirty = False
    window.close_file()
    window.recent_files = []
    window.workspace_pages.empty_page.set_recent_paths(())
    window.workspace_shell.close_inspector()
    _settle()
    _set_capture_status(window, 'Ready to open an image dataset')


def _first_image_fit(window):
    _clear_capture_save_state(window)
    context = _context(window)
    expected_path = os.path.abspath(context.image_path)
    current_path = (os.path.abspath(window.file_path)
                    if window.file_path else None)
    if (window.document_kind != DocumentKind.IMAGE
            or current_path != expected_path):
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        # Publish the declared fixture directly.  The output directory may
        # share its parent during tests, so scanning it could select a prior
        # PNG artifact instead of the named sample image.
        assert window.load_file(expected_path)
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
    _begin_held_save(window)
    assert window.continuous_save.state == 'saving'
    _settle()
    _set_capture_status(window, 'Saving annotation')


def _saved(window):
    _two_rectangles(window)
    assert window.continuous_save.state == 'saved'
    _settle()
    _set_capture_status(window, 'Annotation saved')


def _save_failed(window):
    _two_rectangles(window)
    coordinator = window.continuous_save
    ticket = _begin_held_save(window)
    coordinator.fail(ticket, 'Deterministic screenshot failure')
    assert coordinator.state == 'failed'
    _settle()
    _set_capture_status(window, 'Save failed; retry is available')


def _capture_video_snapshot():
    """Build a small in-memory video session without optional decoding."""
    fingerprint = VideoFingerprint(4096, 1, 'ux-capture-video')
    frame_ref = VideoFrameRef(fingerprint, 0, 2000, 1, 1000)
    image = QImage(640, 360, QImage.Format_RGB32)
    image.fill(QColor('#385575'))
    byte_size = (image.sizeInBytes() if hasattr(image, 'sizeInBytes')
                 else image.byteCount())
    first = VideoFrameResult(
        frame_ref, image, 640, 360, 640, 360, 0, byte_size,
        'ux-capture-video:2000')
    return VideoSessionSnapshot(
        'deterministic-capture.mp4', None, fingerprint, 0, 1, 1000,
        640, 360, 0, 'fixture', 10_000, 0, 24, 1, 0, first)


def _video_workspace(window):
    """Project a real timeline from a deterministic in-memory session."""
    _clear_capture_save_state(window)
    snapshot = _capture_video_snapshot()
    window.pause_video()
    window._set_document_kind(DocumentKind.VIDEO)
    window.video_snapshot = snapshot
    window.current_video_frame_ref = snapshot.initial_frame.frame_ref
    window.video_timeline.set_session(snapshot)
    window.video_timeline.set_markers(
        accepted=(2000,), pending=(5000,), propagation=((3000, 4200),))
    window.canvas.load_pixmap(QPixmap.fromImage(snapshot.initial_frame.image))
    window.canvas.setEnabled(True)
    window.workspace_pages.set_page('canvas')
    return snapshot


def _video_paused(window):
    _video_workspace(window)
    window.video_timeline.set_playing(False)
    _settle()
    _set_capture_status(window, 'Video paused at 00:00:02.000')


def _video_playing(window):
    _video_workspace(window)
    # The timeline owns the visual playback projection; no decoder is started.
    window.video_timeline.set_playing(True)
    _settle()
    _set_capture_status(window, 'Video playing at 1x')


def _video_invalid_time(window):
    _video_workspace(window)
    timeline = window.video_timeline
    timeline.time_edit.setText('99:99:99.999')
    timeline._emit_time_seek()
    assert timeline.time_edit.isModified()
    _settle()
    _set_capture_status(window, 'Use HH:MM:SS.mmm within the video duration')


def _video_track_menu(window):
    _video_workspace(window)
    timeline = window.video_timeline
    menu = timeline.track_menu
    if not hasattr(window, '_ux_capture_track_menu_flags'):
        window._ux_capture_track_menu_flags = menu.windowFlags()
    # A popup QMenu is a separate native window and is omitted by window.grab.
    # Embed the actual menu as a temporary child for one deterministic full-
    # window capture; the menu actions remain the production action objects.
    menu.setWindowFlags(Qt.Widget)
    menu.setGeometry(
        max(0, timeline.width() - 190), 2, 188,
        max(80, menu.sizeHint().height()))
    menu.show()
    assert menu.isVisible()
    _settle()
    _set_capture_status(window, 'Track menu open')


def _video_propagation_pending(window):
    _video_workspace(window)
    timeline = window.video_timeline
    timeline.set_propagation_review(3, gaps=1, failures=0)
    timeline.set_markers(pending=(4000, 5000, 6000), gaps=((7000, 7600),))
    assert timeline.progress_label.isVisible()
    _settle()
    _set_capture_status(window, 'Propagation review has 3 pending results')


def _show_assist(window):
    window.workspace_pages.set_page('canvas')
    window.workspace_pages.show_assist()
    window._project_assist(window._assist_download_progress)
    assert window.workspace_pages.assist_panel.isVisible()


def _assist_setup(window):
    _first_image_fit(window)
    window.assist_state.require_setup(MOBILE_SAM_MANIFEST.model_id)
    window._assist_download_progress = None
    _show_assist(window)
    _settle()
    _set_capture_status(window, 'Assist setup is required')


def _assist_downloading(window):
    _first_image_fit(window)
    window.assist_state.ready_to_download(MOBILE_SAM_MANIFEST.model_id)
    window.assist_state.start_download()
    artifact = MOBILE_SAM_MANIFEST.artifacts[0]
    window._assist_download_progress = ModelDownloadProgress(
        artifact.name, artifact.size // 2, artifact.size,
        artifact.size // 2, MOBILE_SAM_MANIFEST.total_size)
    _show_assist(window)
    _settle()
    _set_capture_status(window, 'Downloading Assist model')


def _assist_failure(window):
    _first_image_fit(window)
    window.assist_state.ready_to_download(MOBILE_SAM_MANIFEST.model_id)
    window.assist_state.fail(
        AssistFailureKind.OFFLINE, 'Deterministic capture provider failure.')
    window._assist_download_progress = None
    _show_assist(window)
    _settle()
    _set_capture_status(window, 'Assist download failed; retry is available')


def _assist_preview(window):
    _first_image_fit(window)
    window.sam_output_mode = 'box'
    window.assist_state.ready(MOBILE_SAM_MANIFEST.model_id)
    window.assist_state.start_run(window._dataset_generation)
    window._assist_document_identity = window.document_identity
    window._assist_prompt = None
    window._on_assist_preview(
        window._dataset_generation,
        SamResult(
            polygon=((80.0, 70.0), (280.0, 70.0), (280.0, 230.0)),
            bounds=(80.0, 70.0, 280.0, 230.0)))
    assert window.assist_state.snapshot.phase is AssistPhase.PREVIEW
    _show_assist(window)
    _settle()
    _set_capture_status(window, 'Assist preview is ready for review')


def _shutdown_timeout(window):
    _empty_workspace(window)
    window._show_shutdown_timeout(('video decode', 'Assist download'))
    assert window._shutdown_surface.isVisible()
    _settle()


SCENARIOS = {
    'empty-workspace': _empty_workspace,
    'first-image-fit': _first_image_fit,
    'two-rectangles': _two_rectangles,
    'inspector-open': _inspector_open,
    'inspector-closed': _inspector_closed,
    'saving': _saving,
    'saved': _saved,
    'save-failed': _save_failed,
    'video-paused': _video_paused,
    'video-playing': _video_playing,
    'video-invalid-time': _video_invalid_time,
    'video-track-menu': _video_track_menu,
    'video-propagation-pending': _video_propagation_pending,
    'assist-setup': _assist_setup,
    'assist-downloading': _assist_downloading,
    'assist-failure': _assist_failure,
    'assist-preview': _assist_preview,
    'shutdown-timeout': _shutdown_timeout,
}

SCENARIO_SAVE_STATES = {
    'first-image-fit': 'saved',
    'two-rectangles': 'saved',
    'inspector-open': 'saved',
    'inspector-closed': 'saved',
    'saving': 'saving',
    'saved': 'saved',
    'save-failed': 'failed',
}

SCENARIO_SHAPE_COUNTS = {
    'empty-workspace': 0,
    'first-image-fit': 0,
    'two-rectangles': 2,
    'inspector-open': 2,
    'inspector-closed': 2,
    'saving': 2,
    'saved': 2,
    'save-failed': 2,
}


def cleanup_scenario(window):
    """Release only deterministic capture projections, never live workers."""
    _clear_capture_save_state(window)
    timeline = window.video_timeline
    timeline.set_playing(False)
    timeline.track_menu.hide()
    flags = getattr(window, '_ux_capture_track_menu_flags', None)
    if flags is not None:
        timeline.track_menu.setWindowFlags(flags)
        del window._ux_capture_track_menu_flags
    timeline.set_propagation_progress(0, 0, 0, 0, None, 0, running=False)
    timeline.set_propagation_review(0, 0, 0)
    window._hide_shutdown_timeout()
    window.workspace_pages.hide_assist()
    window.canvas.clear_assist_preview()
    window._assist_download_progress = None
    window._assist_prompt = None
    window._assist_document_identity = None
    # Capture setup never starts a worker.  Settle only its visible loading
    # projection; this does not cancel or otherwise control a live worker.
    window._settle_replacement_loading(settle_unowned=True)
    _settle()


def _image_projection_is_ready(window):
    """Return whether the canvas shows the capture context's image document."""
    context = _context(window)
    expected_path = os.path.abspath(context.image_path)
    current_path = (os.path.abspath(window.file_path)
                    if window.file_path else None)
    pixmap = window.canvas.pixmap
    timeline = window.video_timeline
    return (window.document_kind == DocumentKind.IMAGE
            and current_path == expected_path
            and pixmap is not None and not pixmap.isNull()
            and not timeline.isVisible()
            and not timeline.isEnabled()
            and timeline._snapshot is None)


def scenario_is_meaningful(window, scenario):
    """Assert the state owner that makes each named capture truthful."""
    if scenario in SCENARIO_SHAPE_COUNTS:
        expected_save_state = SCENARIO_SAVE_STATES.get(scenario)
        if expected_save_state is not None and \
                window.continuous_save.state != expected_save_state:
            return False
        if scenario == 'empty-workspace':
            return (window.document_kind == DocumentKind.NONE
                    and len(window.canvas.shapes) == 0)
        return (_image_projection_is_ready(window)
                and len(window.canvas.shapes)
                == SCENARIO_SHAPE_COUNTS[scenario])
    if scenario == 'video-paused':
        return (window.document_kind == DocumentKind.VIDEO
                and not window.video_timeline._playing)
    if scenario == 'video-playing':
        return (window.document_kind == DocumentKind.VIDEO
                and window.video_timeline._playing)
    if scenario == 'video-invalid-time':
        return (window.document_kind == DocumentKind.VIDEO
                and window.video_timeline.time_edit.isModified())
    if scenario == 'video-track-menu':
        return (window.document_kind == DocumentKind.VIDEO
                and window.video_timeline.track_menu.isVisible())
    if scenario == 'video-propagation-pending':
        return (window.document_kind == DocumentKind.VIDEO
                and window.video_timeline.progress_label.isVisible()
                and window.video_timeline._propagation_review_counts[0] == 3)
    panel = window.workspace_pages.assist_panel
    if scenario == 'assist-setup':
        return (_image_projection_is_ready(window)
                and panel.isVisible()
                and window.assist_state.snapshot.phase
                is AssistPhase.SETUP_REQUIRED)
    if scenario == 'assist-downloading':
        return (_image_projection_is_ready(window)
                and panel.isVisible()
                and window.assist_state.snapshot.phase
                is AssistPhase.DOWNLOADING
                and window._assist_download_progress is not None)
    if scenario == 'assist-failure':
        return (_image_projection_is_ready(window)
                and panel.isVisible()
                and window.assist_state.snapshot.phase is AssistPhase.FAILED
                and window.assist_state.snapshot.failure_kind
                is AssistFailureKind.OFFLINE)
    if scenario == 'assist-preview':
        return (_image_projection_is_ready(window)
                and panel.isVisible()
                and window.assist_state.snapshot.phase is AssistPhase.PREVIEW
                and window.canvas.assist_preview_shape is not None)
    if scenario == 'shutdown-timeout':
        return (window._shutdown_surface is not None
                and window._shutdown_surface.isVisible())
    return False


def capture_scenario(window, scenario, size, theme, output_dir):
    """Apply one named state and save its full-window PNG."""
    if scenario not in SCENARIOS:
        raise ValueError('unknown capture scenario: %s' % scenario)
    if theme not in THEMES:
        raise ValueError('unknown capture theme: %s' % theme)
    if tuple(size) not in SIZES:
        raise ValueError('unsupported capture size: %s' % (size,))
    original_policy = window.workflow.snapshot.prompt_policy
    original_theme = window._current_theme
    setup_started = False
    completed = False
    try:
        cleanup_scenario(window)
        window.active_class_control.confirm_each.setChecked(False)
        assert window.workflow.snapshot.prompt_policy is \
            PromptPolicy.REUSE_ACTIVE
        window.resize(*size)
        selected_theme = Theme.DARK if theme == 'dark' else Theme.LIGHT
        window._current_theme = selected_theme
        window._apply_theme(selected_theme)
        setup_started = True
        SCENARIOS[scenario](window)
        QApplication.processEvents()
        assert scenario_is_meaningful(window, scenario)
        if SCENARIO_SHAPE_COUNTS.get(scenario):
            assert window.workflow.snapshot.active_class == 'vehicle'
            assert window.workflow.snapshot.active_tool is \
                AnnotationTool.RECTANGLE
        filename = '%s-%s-%sx%s.png' % (
            scenario, theme, size[0], size[1])
        output_dir = os.fspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, filename)
        assert window.grab().save(path, 'PNG')
        completed = True
        return path
    finally:
        try:
            if setup_started and not completed:
                cleanup_scenario(window)
        finally:
            window.active_class_control.confirm_each.setChecked(
                original_policy is PromptPolicy.CONFIRM_EACH)
            if window._current_theme is not original_theme:
                window._current_theme = original_theme
                window._apply_theme(original_theme)


def _write_sample_image(path):
    image = QImage(640, 480, QImage.Format_RGB32)
    image.fill(QColor('#dce6ee'))
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
                    cleanup_scenario(window)
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
