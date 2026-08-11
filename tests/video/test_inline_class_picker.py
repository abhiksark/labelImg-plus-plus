from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtTest import QTest

from labelImgPlusPlus import get_main_app
from libs.core.shape import Shape, ShapeType


def _finalise_rectangle(window):
    shape = Shape(shape_type=ShapeType.RECTANGLE)
    for point in ((10, 10), (40, 10), (40, 30), (10, 30)):
        shape.add_point(QPointF(*point))
    window.canvas.current = shape
    window.canvas.finalise()


def test_video_confirmation_creates_manual_anchor_and_undo_removes_track(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'picker.mp4')
    try:
        assert window.open_video(video)
        window.activate_box_tool()
        _finalise_rectangle(window)
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
        assert not window.video_model.dirty

        window.class_picker.edit.setText('car')
        QTest.keyClick(window.class_picker.edit, Qt.Key_Return)
        app.processEvents()
        assert len(window.video_model.tracks) == 1
        observation = next(iter(window.video_model.observations.values()))
        assert observation.source == 'manual'
        assert observation.review_state == 'accepted'
        assert window.actions.create.isChecked()

        window.undo_action()
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()
