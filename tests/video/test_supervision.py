# tests/video/test_supervision.py
"""Automated annotation must announce itself and stay provisional.

One hand-drawn box used to become dozens of machine annotations written
straight to `accepted` — no confirmation before, no review after, and
indistinguishable from hand-drawn work on export. These tests pin the gates
that stop that.
"""

import time
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QMessageBox

from labelImgPlusPlus import get_main_app
from libs.core.video_types import ObservationRecord


def _close_window(app, window):
    window.dirty = False
    window.close()
    app.processEvents()


def _wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False
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
                          return_value=QMessageBox.StandardButton.Cancel) as ask:
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
                          return_value=QMessageBox.StandardButton.Cancel) as ask:
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


def test_export_prompt_names_review_export_scope_and_cancel(
        tmp_path, make_video):
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'export.mp4', frames=12)))
    try:
        track = _seed(window)
        window.video_model.upsert_tracker(ObservationRecord(
            track.track_id, 4096, [20, 20, 60, 60], source='tracker',
            review_state='pending', anchor=False))
        message = MagicMock()
        buttons = {}

        def add_button(text, _role):
            button = object()
            buttons[text] = button
            return button

        message.addButton.side_effect = add_button
        message.clickedButton.side_effect = lambda: buttons['Cancel']
        with patch('labelImgPlusPlus.QMessageBox', return_value=message):
            assert window._confirm_unreviewed_before_export() == 'cancel'
        assert set(buttons) == {
            'Review suggestions', 'Export accepted-only', 'Cancel'}
    finally:
        _close_window(app, window)


def test_export_is_silent_when_nothing_awaits_review(tmp_path, make_video):
    """The warning must not fire on a fully reviewed document."""
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'clean.mp4', frames=12)))
    try:
        _seed(window)
        with patch.object(QMessageBox, 'question') as ask:
            assert window._confirm_unreviewed_before_export() == 'export'
        assert not ask.called
    finally:
        _close_window(app, window)


def test_reopened_pending_export_review_choice_enters_live_queue(
        tmp_path, make_video):
    app, window = get_main_app()
    video = str(make_video(tmp_path / 'reopen-review.mp4', frames=12))
    try:
        assert window.open_video(video)
        track = _seed(window)
        pts = window.current_video_frame_ref.pts + window._video_step_pts()
        window.video_model.upsert_tracker(ObservationRecord(
            track.track_id, pts, [20, 20, 60, 60], source='tracker',
            review_state='pending', anchor=False))
        window._on_video_model_mutation()
        window.request_save_video_project()
        assert _wait(app, lambda: not window.dirty)
        project = window.video_snapshot.project_path
        assert window.open_video(project)
        assert window._pending_review_keys() == ((track.track_id, pts),)

        with patch.object(
                window, '_confirm_unreviewed_before_export',
                return_value='review'), patch(
                'labelImgPlusPlus.VideoExportDialog') as dialog_cls:
            assert window.open_video_export_dialog() is None

        assert not dialog_cls.called
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == pts)
        assert window._selected_video_track_id == track.track_id
        assert window.actions.primary.text() == 'Accept & Next'
        assert '1 suggestion remaining' in window.statusBar().currentMessage()
    finally:
        _close_window(app, window)


def test_full_run_review_confirms_multi_item_scope_and_stays_one_undo_step(
        tmp_path, make_video):
    app, window = get_main_app()
    window.open_video(str(make_video(tmp_path / 'bulk-review.mp4', frames=12)))
    try:
        track = _seed(window)
        keys = ((track.track_id, 4096), (track.track_id, 8192))
        for track_id, pts in keys:
            window.video_model.upsert_tracker(ObservationRecord(
                track_id, pts, [20, 20, 60, 60], source='tracker',
                review_state='pending', anchor=False))
        window._tracking_run_keys = set(keys)
        window._on_video_model_mutation()
        baseline_undo = len(window.undo_stack)

        with patch.object(QMessageBox, 'question',
                          return_value=QMessageBox.StandardButton.Cancel) as ask:
            assert not window.review_full_propagation('accepted')
        assert ask.called
        assert all(window.video_model.observations[key].review_state ==
                   'pending' for key in keys)

        with patch.object(QMessageBox, 'question',
                          return_value=QMessageBox.StandardButton.Yes):
            assert window.review_full_propagation('accepted')
        assert all(window.video_model.observations[key].review_state ==
                   'accepted' for key in keys)
        assert len(window.undo_stack) == baseline_undo + 1
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
        assert text.count(':') >= 4
        assert 'PTS' in window.label_image_count.toolTip()
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
