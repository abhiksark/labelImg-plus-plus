import os
import time

from PyQt5.QtWidgets import QApplication

from labelImgPlusPlus import get_main_app
from libs.core.video_types import (
    FrameStateRecord, VideoExportRequest,
)
from libs.formats.labelFile import LabelFileFormat
from libs.widgets.videoExportDialog import VideoExportDialog


_APP = QApplication.instance() or QApplication([])


def _wait(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _seed(window):
    model = window.video_model
    track = model.create_track(
        'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
    pts = window.current_video_frame_ref.pts
    model.upsert_manual(track.track_id, pts, [1, 2, 20, 22])
    model.set_frame_verified(pts, True)
    window._on_video_model_mutation()


def test_export_dialog_defaults_to_annotated_jpeg_95():
    dialog = VideoExportDialog(LabelFileFormat.COCO)
    try:
        values = dialog.values()
        assert values['selection'] == 'annotated'
        assert values['image_format'] == 'jpg'
        assert values['jpeg_quality'] == 95
        assert values['annotation_format'] == LabelFileFormat.COCO
    finally:
        dialog.close()


def test_export_dialog_states_the_accepted_and_verified_frame_counts():
    dialog = VideoExportDialog(LabelFileFormat.COCO)
    try:
        dialog.set_frame_counts(7, 3)
        assert dialog.selection.itemText(
            dialog.selection.findData('annotated')) == \
            'Annotated frames (7 accepted)'
        assert dialog.selection.itemText(
            dialog.selection.findData('verified')) == 'Verified frames (3)'
        assert dialog.values()['selection'] == 'annotated'
    finally:
        dialog.close()


def test_main_window_selection_builders_use_exact_pts(tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        _seed(window)
        annotated = window._video_export_frame_refs({
            'selection': 'annotated',
        })
        verified = window._video_export_frame_refs({
            'selection': 'verified',
        })
        assert [item.pts for item in annotated] == \
            [window.current_video_frame_ref.pts]
        assert [item.pts for item in verified] == \
            [window.current_video_frame_ref.pts]
        ranged = window._video_export_frame_refs({
            'selection': 'range',
            'start_time': '00:00:00.000',
            'end_time': '00:00:00.500',
            'sample_unit': 'seconds',
            'sample_seconds': .25,
            'sample_frames': 1,
        })
        assert len(ranged) == 3
        assert all(item.time_base_den > 0 for item in ranged)
    finally:
        window.dirty = False
        window.close()


def test_public_export_request_runs_in_background_and_publishes(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    destination = str(tmp_path / 'published')
    try:
        assert window.open_video(video)
        _seed(window)
        state = window.video_model.snapshot_state()
        request = VideoExportRequest(
            source_path=window.video_snapshot.source_path,
            project_path=window.video_snapshot.project_path,
            destination=destination,
            stream_index=window.video_snapshot.stream_index,
            frame_refs=(window.current_video_frame_ref,),
            observations=state.observations,
            tracks=state.tracks,
            frame_states=(FrameStateRecord(
                window.current_video_frame_ref.pts, True, 1),),
            annotation_format=LabelFileFormat.PASCAL_VOC,
            class_order=state.classes)
        handle = window.request_export_video(request)
        assert handle is not None
        assert _wait(app, lambda: window._video_export_handle is None)
        assert os.path.isdir(destination)
        assert os.path.isfile(os.path.join(
            destination, 'video_export_manifest.json'))
        assert 'Exported video frames' in window.statusBar().currentMessage()
    finally:
        window.dirty = False
        window.close()
