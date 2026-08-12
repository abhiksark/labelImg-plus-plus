# tests/video/test_supervision.py
"""Automated annotation must announce itself and stay provisional.

One hand-drawn box used to become dozens of machine annotations written
straight to `accepted` — no confirmation before, no review after, and
indistinguishable from hand-drawn work on export. These tests pin the gates
that stop that.
"""

from unittest.mock import patch

from PyQt5.QtWidgets import QDialog, QMessageBox

from labelImgPlusPlus import get_main_app
from libs.core.video_types import ObservationRecord


def _close_window(app, window):
    window.dirty = False
    window.close()
    app.processEvents()
    app.processEvents()


def _seed(window, track_id='track-1'):
    model = window.video_model
    track = model.create_track('object', 'rectangle', (0, 255, 0, 255),
                               track_id=track_id)
    model.upsert_manual(track.track_id,
                        window.current_video_frame_ref.pts, [16, 14, 52, 50])
    window._selected_video_track_id = track.track_id
    window._on_video_model_mutation()
    window._materialize_video_frame(window.current_video_frame_ref.pts)
    return track


def test_a_sweeping_run_asks_before_it_starts(tmp_path, make_video):
    """Declining must abort before any work is dispatched."""
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'confirm.mp4', frames=12)))
    try:
        _seed(window)
        with patch.object(QMessageBox, 'question',
                          return_value=QMessageBox.Cancel) as ask:
            handle = window.propagate_across_video()
        assert ask.called, 'a sweeping run must confirm its scope'
        assert handle is None
        assert window._propagation_handle is None
        assert window._active_propagation_request is None
    finally:
        _close_window(app, window)


def test_the_confirmation_states_the_real_scope(tmp_path, make_video):
    """The message must carry the track count and a frame estimate."""
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'scope.mp4', frames=12)))
    try:
        _seed(window)
        with patch.object(QMessageBox, 'question',
                          return_value=QMessageBox.Cancel) as ask:
            window.propagate_across_video()
        message = ask.call_args[0][2]
        assert '1 track' in message
        assert 'frames' in message or 'remainder' in message
        assert 'review' in message.lower()
    finally:
        _close_window(app, window)


def test_the_narrow_directional_path_does_not_double_prompt(
        tmp_path, make_video):
    """Track Forward already asks for an endpoint; that is its gate."""
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'directional.mp4', frames=12)))
    try:
        _seed(window)
        with patch.object(QMessageBox, 'question') as ask:
            with patch.object(window, '_choose_tracking_endpoint',
                              return_value=None):
                window.track_selected_forward(choose_endpoint=True)
        assert not ask.called
    finally:
        _close_window(app, window)


def test_export_warns_while_suggestions_await_review(tmp_path, make_video):
    """Unreviewed work is omitted from export, so it must not be silent."""
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'export.mp4', frames=12)))
    try:
        track = _seed(window)
        window.video_model.upsert_tracker(ObservationRecord(
            track.track_id, 4096, [20, 20, 60, 60], source='tracker',
            review_state='pending', anchor=False))
        # Stub the export dialog itself: without the warning the flow would
        # reach a real modal and hang the suite instead of failing.
        with patch('labelImgPlusPlus.VideoExportDialog') as dialog_cls:
            dialog_cls.return_value.exec_.return_value = QDialog.Rejected
            with patch.object(QMessageBox, 'question',
                              return_value=QMessageBox.Cancel) as ask:
                assert window.open_video_export_dialog() is None
            assert ask.called, 'export must warn about unreviewed suggestions'
            assert 'review' in ask.call_args[0][2].lower()
            assert not dialog_cls.called, \
                'cancelling the warning must abort before the export dialog'
    finally:
        _close_window(app, window)


def test_export_is_silent_when_nothing_awaits_review(tmp_path, make_video):
    """The warning must not fire on a fully reviewed document."""
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'clean.mp4', frames=12)))
    try:
        _seed(window)
        with patch.object(QMessageBox, 'question') as ask:
            assert window._confirm_unreviewed_before_export() is True
        assert not ask.called
    finally:
        _close_window(app, window)


def test_the_status_strip_shows_a_frame_position_for_video(
        tmp_path, make_video):
    """"Image: 0 / 0" is meaningless for a clip."""
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'strip.mp4', frames=12)))
    try:
        window.update_image_count()
        text = window.label_image_count.text()
        assert 'Image:' not in text
        assert 'Frame' in text or 'PTS' in text
    finally:
        _close_window(app, window)


def test_the_bulk_review_actions_have_shortcuts(tmp_path, make_video):
    """Reviewing a run is the primary workflow, not a menu-only afterthought."""
    app, window = get_main_app()
    try:
        assert window.actions.videoAcceptRun.shortcut().toString()
        assert window.actions.videoRejectRun.shortcut().toString()
        assert (window.actions.videoAcceptRun.shortcut()
                != window.actions.videoRejectRun.shortcut())
    finally:
        window.dirty = False
