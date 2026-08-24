import builtins
from dataclasses import FrozenInstanceError, replace
import importlib.util
import sys
import types

import pytest
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QKeySequence
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAction, QApplication, QStyle, QStyleFactory

from libs.core.video_decoder import VideoDecoderSession
from libs.core.video_types import (
    VideoFingerprint, VideoFrameRef, VideoFrameResult, VideoSessionSnapshot,
)
from libs.widgets.videoTimelineWidget import (
    TIMELINE_MAX, VideoTimelineWidget, format_timecode, parse_timecode,
)
from libs.widgets import videoTimelineWidget as timeline_module
from libs.utils.styles import get_combined_style


_APP = QApplication.instance() or QApplication([])


@pytest.fixture
def video_snapshot():
    fingerprint = VideoFingerprint(1024, 123, 'timeline-fixture')
    frame_ref = VideoFrameRef(fingerprint, 0, 3400, 1, 1000)
    image = QImage(96, 64, QImage.Format_RGB32)
    byte_size = (image.sizeInBytes() if hasattr(image, 'sizeInBytes')
                 else image.byteCount())
    first = VideoFrameResult(
        frame_ref, image, 96, 64, 96, 64, 0,
        byte_size, 'timeline-fixture:0:3400')
    return VideoSessionSnapshot(
        'timeline.mp4', None, fingerprint, 0, 1, 1000,
        96, 64, 0, 'fixture', 10_000, 900, 12, 1, 0, first)


def test_play_button_names_and_depicts_the_current_action():
    widget = VideoTimelineWidget()
    playback = QAction('Play/Pause Video', widget)
    playback.setShortcut(QKeySequence('Alt+P'))
    try:
        widget.set_playback_action(playback)
        shortcut = playback.shortcut().toString(QKeySequence.NativeText)
        widget.set_playing(False)
        assert widget.play_button.accessibleName() == 'Play video'
        assert widget.play_button.toolTip() == \
            'Play video (%s)' % shortcut
        assert widget.play_button.isChecked() is False
        assert widget.play_button.icon().pixmap(16, 16).toImage() == \
            widget.style().standardIcon(
                QStyle.SP_MediaPlay).pixmap(16, 16).toImage()

        widget.set_playing(True)
        assert widget.play_button.accessibleName() == 'Pause video'
        assert widget.play_button.toolTip() == \
            'Pause video (%s)' % shortcut
        assert widget.play_button.isChecked() is True
        assert widget.play_button.icon().pixmap(16, 16).toImage() == \
            widget.style().standardIcon(
                QStyle.SP_MediaPause).pixmap(16, 16).toImage()
    finally:
        widget.close()


def test_play_tooltip_tracks_live_native_action_shortcut_without_copying_it():
    widget = VideoTimelineWidget()
    playback = QAction('Play/Pause Video', widget)
    playback.setShortcut(QKeySequence('Ctrl+Space'))
    try:
        widget.set_playback_action(playback)
        widget.set_playing(True)
        assert widget.play_button.shortcut().isEmpty()
        assert playback.shortcut() == QKeySequence('Ctrl+Space')

        playback.setShortcut(QKeySequence('Meta+Shift+P'))
        QApplication.processEvents()
        native = playback.shortcut().toString(QKeySequence.NativeText)
        assert widget.play_button.toolTip() == \
            'Pause video (%s)' % native
        assert playback.shortcut().toString(QKeySequence.PortableText) == \
            'Meta+Shift+P'
        assert widget.play_button.shortcut().isEmpty()
    finally:
        widget.close()


def test_compact_timeline_keeps_essential_controls_visible():
    widget = VideoTimelineWidget()
    propagate_all = QAction('Propagate across video', widget)
    propagate_selected = QAction('Propagate selected object', widget)
    cancel = QAction('Cancel propagation', widget)
    widget.set_propagation_actions(
        propagate_all, propagate_selected, cancel)
    try:
        widget.resize(748, 96)
        widget.show()
        QApplication.processEvents()

        assert widget.layout_mode == 'compact'
        assert all(control.isVisible() for control in (
            widget.previous_button, widget.play_button, widget.next_button,
            widget.time_edit, widget.speed_combo, widget.slider,
        ))
        assert widget.track_button.isVisible()
        assert widget.track_button.accessibleName() == 'Track'
        assert widget.track_menu.title() == 'Track'
        assert widget.track_menu.actions() == [
            propagate_all, propagate_selected, cancel]
        assert all(control.minimumHeight() >= 32 for control in (
            widget.previous_button, widget.play_button, widget.next_button,
            widget.time_edit, widget.speed_combo,
        ))
        assert widget.slider.geometry().bottom() < \
            widget.play_button.geometry().top()
        assert not any(control.isVisible() for control in (
            widget.propagate_all_button,
            widget.propagate_selected_button,
            widget.cancel_propagation_button,
        ))
    finally:
        widget.close()


def test_seek_slider_has_a_32_pixel_pointer_target_with_production_style():
    widget = VideoTimelineWidget()
    production_style = QStyleFactory.create('Fusion')
    widget.setStyle(production_style)
    widget.setStyleSheet(get_combined_style())
    try:
        widget.resize(748, 96)
        widget.show()
        QApplication.processEvents()

        target = widget.slider.rect()
        assert target.width() >= 32
        assert target.height() >= 32
        assert widget.slider.minimumHeight() >= 32
        assert widget.slider.geometry().bottom() < \
            widget.play_button.geometry().top()
        assert widget.layout_mode == 'compact'
    finally:
        widget.close()


def test_wide_mode_uses_live_control_measurements():
    widget = VideoTimelineWidget()
    propagate_all = QAction('Propagate across video', widget)
    propagate_selected = QAction('Propagate selected object', widget)
    cancel = QAction('Cancel propagation', widget)
    widget.set_propagation_actions(
        propagate_all, propagate_selected, cancel)
    try:
        widget.resize(1400, 96)
        widget.show()
        QApplication.processEvents()
        assert widget.layout_mode == 'wide'
        assert widget.propagate_all_button.isVisible()
        assert widget.propagate_selected_button.isVisible()
        assert not widget.track_button.isVisible()

        propagate_selected.setText('Track ' + ('selected objects ' * 20))
        widget.resize(1399, 96)
        widget.resize(1400, 96)
        QApplication.processEvents()
        assert widget.layout_mode == 'compact'
        assert widget.track_button.isVisible()
        assert not widget.propagate_selected_button.isVisible()
    finally:
        widget.close()


def test_position_prioritizes_frame_and_time_while_pts_stays_in_tooltip(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        assert widget.position_label.text() == \
            'Frame ~30 · 00:00:02.500'
        assert widget.position_label.toolTip() == 'PTS 3400'
    finally:
        widget.close()


@pytest.mark.parametrize('seconds, expected', [
    (0, '00:00:00.000'),
    (1.234, '00:00:01.234'),
    (3661.999, '01:01:01.999'),
])
def test_timecode_round_trip(seconds, expected):
    assert format_timecode(seconds) == expected
    assert parse_timecode(expected) == pytest.approx(seconds)


@pytest.mark.parametrize('value', [
    '00:00:02.000d',
    '0:00:02.000',
    '00:60:00.000',
    '00:00:60.000',
])
def test_timecode_rejects_noncanonical_values(value):
    with pytest.raises(ValueError):
        parse_timecode(value)


def test_timecode_editor_validator_matches_canonical_contract():
    widget = VideoTimelineWidget()
    try:
        widget.time_edit.setText('0:00:02.000')
        assert widget.time_edit.hasAcceptableInput() is False
        widget.time_edit.setText('00:00:02.000')
        assert widget.time_edit.hasAcceptableInput() is True
    finally:
        widget.close()


def test_module_constructs_through_true_pyqt4_fallback(monkeypatch):
    qt4 = types.ModuleType('PyQt4')
    qt4.__path__ = []
    qt_core = types.ModuleType('PyQt4.QtCore')
    qt_gui = types.ModuleType('PyQt4.QtGui')
    for name in ('QEvent', 'QRegExp', 'Qt', 'QTimer', 'pyqtSignal'):
        setattr(qt_core, name, getattr(QtCore, name))
    for name in (
            'QColor', 'QPainter', 'QPen', 'QRegExpValidator',
            'QComboBox', 'QHBoxLayout', 'QKeySequence', 'QLabel', 'QLineEdit',
            'QMenu', 'QPushButton', 'QSizePolicy', 'QSlider', 'QStyle',
            'QToolButton', 'QVBoxLayout', 'QWidget'):
        source = QtGui if hasattr(QtGui, name) else QtWidgets
        setattr(qt_gui, name, getattr(source, name))
    qt4.QtCore = qt_core
    qt4.QtGui = qt_gui

    real_import = builtins.__import__

    def import_without_pyqt5(name, *args, **kwargs):
        if name.startswith('PyQt5'):
            raise ImportError('exercise the supported PyQt4 branch')
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as isolated:
        isolated.setitem(sys.modules, 'PyQt4', qt4)
        isolated.setitem(sys.modules, 'PyQt4.QtCore', qt_core)
        isolated.setitem(sys.modules, 'PyQt4.QtGui', qt_gui)
        isolated.setattr(builtins, '__import__', import_without_pyqt5)
        spec = importlib.util.spec_from_file_location(
            'video_timeline_pyqt4_fallback', timeline_module.__file__)
        fallback = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fallback)
        widget = fallback.VideoTimelineWidget()
        try:
            widget.time_edit.setText('0:00:02.000')
            assert widget.time_edit.hasAcceptableInput() is False
            widget.time_edit.setText('00:00:02.000')
            assert widget.time_edit.hasAcceptableInput() is True
        finally:
            widget.close()


def test_module_constructs_with_legacy_pyqt5_validator(monkeypatch):
    real_import = builtins.__import__

    def import_without_regular_expression(
            name, globals=None, locals=None, fromlist=(), level=0):
        if (name in ('PyQt5.QtCore', 'PyQt5.QtGui')
                and any(item.startswith('QRegularExpression')
                        for item in fromlist)):
            raise ImportError('QRegularExpression is unavailable')
        return real_import(name, globals, locals, fromlist, level)

    with monkeypatch.context() as isolated:
        isolated.setattr(
            builtins, '__import__', import_without_regular_expression)
        spec = importlib.util.spec_from_file_location(
            'video_timeline_legacy_pyqt5', timeline_module.__file__)
        fallback = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fallback)
        widget = fallback.VideoTimelineWidget()
        try:
            widget.time_edit.setText('0:00:02.000')
            assert widget.time_edit.hasAcceptableInput() is False
            widget.time_edit.setText('00:00:02.000')
            assert widget.time_edit.hasAcceptableInput() is True
        finally:
            widget.close()


def test_accessibility_style_value_change_emits_seek(video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        spy = QSignalSpy(widget.seekRequested)
        widget.slider.setValue(TIMELINE_MAX // 2)
        if not spy:
            assert spy.wait(100)
        assert len(spy) == 1
    finally:
        widget.close()


def test_keyboard_slider_value_change_emits_seek(video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        widget.slider.setFocus(Qt.OtherFocusReason)
        spy = QSignalSpy(widget.seekRequested)
        QTest.keyClick(widget.slider, Qt.Key_Right)
        if not spy:
            assert spy.wait(100)
        assert len(spy) == 1
    finally:
        widget.close()


def test_mouse_release_cancels_debounce_and_emits_one_final_seek(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        spy = QSignalSpy(widget.seekRequested)
        widget._slider_pressed()
        widget.slider.setValue(TIMELINE_MAX // 2)
        widget._slider_released()
        QTest.qWait(75)
        assert len(spy) == 1
    finally:
        widget.close()


def test_mouse_release_preserves_user_value_across_internal_projection(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        spy = QSignalSpy(widget.seekRequested)
        widget._slider_pressed()
        widget.slider.setValue(TIMELINE_MAX // 2)
        widget.set_current_frame(video_snapshot.initial_frame.frame_ref)

        widget._slider_released()
        QTest.qWait(75)

        assert len(spy) == 1
        assert spy[0][0].pts == 5900
    finally:
        widget.close()


def test_mouse_release_does_not_duplicate_debounced_value_after_projection(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        spy = QSignalSpy(widget.seekRequested)
        widget._slider_pressed()
        widget.slider.setValue(TIMELINE_MAX // 2)
        assert spy.wait(100)
        widget.set_current_frame(video_snapshot.initial_frame.frame_ref)

        widget._slider_released()
        QTest.qWait(75)

        assert len(spy) == 1
        assert spy[0][0].pts == 5900
    finally:
        widget.close()


def test_internal_position_projection_never_emits_seek(video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        prior_intent = QSignalSpy(widget.seekRequested)
        widget.slider.setValue(TIMELINE_MAX // 2)
        if not prior_intent:
            assert prior_intent.wait(100)
        assert len(prior_intent) == 1
        spy = QSignalSpy(widget.seekRequested)
        changed = QSignalSpy(widget.slider.valueChanged)
        widget.set_current_frame(video_snapshot.initial_frame.frame_ref)
        QApplication.processEvents()
        assert len(changed) == 1
        assert len(spy) == 0
        assert widget._projecting_position is False
    finally:
        widget.close()


def test_pending_user_seek_keeps_its_value_during_internal_projection(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        spy = QSignalSpy(widget.seekRequested)
        widget.slider.setValue(TIMELINE_MAX // 2)
        widget.set_current_frame(video_snapshot.initial_frame.frame_ref)
        if not spy:
            assert spy.wait(100)
        assert len(spy) == 1
        expected_pts = (video_snapshot.start_pts
                        + round(video_snapshot.duration_pts / 2))
        assert spy[0][0].pts == expected_pts
    finally:
        widget.close()


@pytest.mark.parametrize('value', [
    'not-a-time',
    '00:00:02.000d',
])
def test_timecode_invalid_return_emits_error_without_seek_or_rewrite(
        video_snapshot, value):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        widget.show()
        widget.activateWindow()
        widget.time_edit.setFocus(Qt.OtherFocusReason)
        widget.time_edit.setText(value)
        QApplication.processEvents()
        assert widget.time_edit.hasFocus()
        errors = QSignalSpy(widget.timeInputError)
        seeks = QSignalSpy(widget.seekRequested)

        QTest.keyClick(widget.time_edit, Qt.Key_Return)
        QApplication.processEvents()

        assert len(errors) == 1
        assert len(seeks) == 0
        assert widget.time_edit.text() == value
        assert widget.time_edit.hasFocus()
    finally:
        widget.close()


def test_timecode_out_of_range_return_emits_error_without_seek_or_rewrite(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        widget.show()
        duration = (video_snapshot.duration_pts
                    * video_snapshot.time_base_num
                    / video_snapshot.time_base_den)
        invalid = format_timecode(duration + 1.0)
        widget.time_edit.setFocus(Qt.OtherFocusReason)
        widget.time_edit.setText(invalid)
        errors = QSignalSpy(widget.timeInputError)
        seeks = QSignalSpy(widget.seekRequested)

        QTest.keyClick(widget.time_edit, Qt.Key_Return)
        QApplication.processEvents()

        assert len(errors) == 1
        assert len(seeks) == 0
        assert widget.time_edit.text() == invalid
        assert widget.time_edit.hasFocus()
    finally:
        widget.close()


def test_timecode_huge_canonical_hours_stay_in_error_only_path(
        video_snapshot):
    value = '%s:00:00.000' % ('9' * 400)
    with pytest.raises(ValueError):
        parse_timecode(value)

    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        widget.show()
        widget.activateWindow()
        widget.time_edit.setFocus(Qt.OtherFocusReason)
        widget.time_edit.setText(value)
        QApplication.processEvents()
        assert widget.time_edit.hasFocus()
        errors = QSignalSpy(widget.timeInputError)
        seeks = QSignalSpy(widget.seekRequested)

        QTest.keyClick(widget.time_edit, Qt.Key_Return)
        QApplication.processEvents()

        assert len(errors) == 1
        assert len(seeks) == 0
        assert widget.time_edit.text() == value
        assert widget.time_edit.hasFocus()
    finally:
        widget.close()


def test_projection_after_invalid_return_preserves_text_until_escape(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        widget.time_edit.setText('invalid')
        errors = QSignalSpy(widget.timeInputError)
        widget._emit_time_seek()
        assert len(errors) == 1

        projected = replace(
            video_snapshot.initial_frame.frame_ref, pts=5900)
        widget.set_current_frame(projected)

        assert widget.time_edit.text() == 'invalid'
        focus_returns = QSignalSpy(widget.focusReturnRequested)
        QTest.keyClick(widget.time_edit, Qt.Key_Escape)
        assert widget.time_edit.text() == '00:00:05.000'
        assert len(focus_returns) == 1
    finally:
        widget.close()


def test_projection_while_editing_preserves_text_and_updates_escape_target(
        video_snapshot):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        widget.time_edit.setText('00:00:04')
        widget.time_edit.setModified(True)

        projected = replace(
            video_snapshot.initial_frame.frame_ref, pts=6900)
        widget.set_current_frame(projected)

        assert widget.time_edit.text() == '00:00:04'
        focus_returns = QSignalSpy(widget.focusReturnRequested)
        QTest.keyClick(widget.time_edit, Qt.Key_Escape)
        assert widget.time_edit.text() == '00:00:06.000'
        assert len(focus_returns) == 1
    finally:
        widget.close()


@pytest.mark.parametrize('value, expected_pts', [
    ('00:00:02.345', 3245),
    ('00:00:10.000', 10_900),
])
def test_timecode_valid_return_emits_one_exact_immutable_frame_reference(
        video_snapshot, value, expected_pts):
    widget = VideoTimelineWidget()
    try:
        widget.set_session(video_snapshot)
        widget.time_edit.setText(value)
        seeks = QSignalSpy(widget.seekRequested)

        widget.time_edit.returnPressed.emit()

        assert len(seeks) == 1
        frame_ref = seeks[0][0]
        assert frame_ref == VideoFrameRef(
            video_snapshot.fingerprint, video_snapshot.stream_index,
            expected_pts, video_snapshot.time_base_num,
            video_snapshot.time_base_den)
        with pytest.raises(FrozenInstanceError):
            frame_ref.pts = 0
    finally:
        widget.close()


def test_internal_session_projection_never_emits_seek(video_snapshot):
    widget = VideoTimelineWidget()
    try:
        spy = QSignalSpy(widget.seekRequested)
        changed = QSignalSpy(widget.slider.valueChanged)

        widget.set_session(video_snapshot)
        QTest.qWait(75)

        assert len(changed) == 1
        assert len(spy) == 0
        assert widget._projecting_position is False
    finally:
        widget.close()


def test_normalized_slider_handles_long_duration_without_overflow(
        tmp_path, make_video):
    path = make_video(tmp_path / 'clip.mp4')
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        snapshot = decoder.snapshot(None, first)
        snapshot = replace(snapshot, duration_pts=10 ** 15)
        widget = VideoTimelineWidget()
        widget.set_session(snapshot)
        ref = replace(first.frame_ref, pts=5 * 10 ** 14)
        widget.set_current_frame(ref)
        assert 0 <= widget.slider.value() <= TIMELINE_MAX
        assert abs(widget.slider.value() - TIMELINE_MAX // 2) <= 1
        widget.close()
    finally:
        decoder.close()


def test_release_emits_exact_frame_reference(tmp_path, make_video):
    path = make_video(tmp_path / 'clip.mp4')
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        snapshot = decoder.snapshot(None, first)
        widget = VideoTimelineWidget()
        widget.set_session(snapshot)
        spy = QSignalSpy(widget.seekRequested)
        widget.slider.setValue(TIMELINE_MAX // 2)
        widget._slider_released()
        assert len(spy) == 1
        ref = spy[0][0]
        assert ref.stream_index == snapshot.stream_index
        assert ref.time_base_den == snapshot.time_base_den
        widget.close()
    finally:
        decoder.close()


def test_invalid_timecode_does_not_emit():
    widget = VideoTimelineWidget()
    spy = QSignalSpy(widget.seekRequested)
    widget.time_edit.setText('not-a-time')
    widget._emit_time_seek()
    assert len(spy) == 0
    widget.close()


def test_propagation_actions_and_progress_replace_each_other():
    widget = VideoTimelineWidget()
    propagate_all = QAction('Propagate across video', widget)
    propagate_selected = QAction('Propagate selected object', widget)
    cancel = QAction('Cancel', widget)
    widget.set_propagation_actions(
        propagate_all, propagate_selected, cancel)
    widget.resize(1400, 96)
    widget.show()
    QApplication.processEvents()
    assert widget.layout_mode == 'wide'
    assert widget.propagate_all_button.defaultAction() is propagate_all
    assert widget.propagate_selected_button.defaultAction() is \
        propagate_selected

    widget.set_propagation_progress(
        12, 40, 2, 1, 3.25, 4, running=True)
    assert widget.progress_label.isHidden() is False
    assert widget.cancel_propagation_button.isHidden() is False
    assert widget.propagate_all_button.isHidden() is True
    assert '12/40 frames' in widget.progress_label.text()
    assert '4 gaps/failures' in widget.progress_label.text()

    widget.set_propagation_progress(
        0, 0, 0, 0, None, 0, running=False)
    assert widget.progress_label.isHidden() is True
    assert widget.cancel_propagation_button.isHidden() is True
    assert widget.propagate_all_button.isHidden() is False
    widget.close()
