#!/usr/bin/env python
# tests/integration/test_main_window.py
"""Tests for MainWindow core functionality.

Tests cover:
- File operations (load, save)
- Image navigation
- Annotation operations
- Mode switching
"""
import os
import sys
import tempfile
import shutil
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QImage

from labelImgPlusPlus import get_main_app
from libs.core.shape import Shape


class TestMainWindowFileOperations(unittest.TestCase):
    """Tests for file loading and saving."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        # Create test images
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset state before each test."""
        self.win.reset_state()
        self.win.default_save_dir = self.temp_dir

    def test_load_file_valid_image(self):
        """Test loading a valid image file."""
        self.win.load_file(self.test_image_path)
        self.assertEqual(self.win.file_path, self.test_image_path)
        self.assertFalse(self.win.image.isNull())

    def test_load_file_nonexistent(self):
        """Test loading a non-existent file."""
        fake_path = os.path.join(self.temp_dir, 'nonexistent.png')
        self.win.load_file(fake_path)
        # Should not crash, file_path should be unchanged or empty
        self.assertNotEqual(self.win.file_path, fake_path)

    def test_load_file_on_annotation_file_does_not_crash(self):
        """Opening an annotation file (suffix == LabelFile.suffix) must fail
        gracefully, not crash.

        Regression: the is_label_file branch in load_file referenced
        LabelFile.lineColor (which does not exist) and left `image` unbound,
        raising AttributeError/UnboundLocalError instead of reporting a clean
        error.
        """
        from unittest.mock import patch
        from libs.formats.labelFile import LabelFile
        annot_path = os.path.join(self.temp_dir, 'annotation' + LabelFile.suffix)
        with open(annot_path, 'w') as f:
            f.write('<annotation><filename>x.jpg</filename></annotation>')

        # error_message shows a modal QMessageBox; stub it so the test does
        # not block, while still exercising the real load_file branch.
        with patch.object(self.win, 'error_message') as mock_error:
            result = self.win.load_file(annot_path)

        self.assertFalse(result)
        self.assertNotEqual(self.win.file_path, annot_path)
        mock_error.assert_called_once()

    def test_default_predefined_classes_file_is_packaged(self):
        """The default class list must ship inside the libs package so it is
        present in the installed wheel (not just the source checkout)."""
        import libs
        packaged = os.path.join(os.path.dirname(libs.__file__),
                                'data', 'predefined_classes.txt')
        self.assertTrue(os.path.isfile(packaged))

    def test_apply_label_fix_does_not_crash(self):
        """_apply_label_fix must use statusBar(), not a missing status_bar attr.

        Regression: it called self.status_bar.showMessage (no such attribute),
        so the label-consistency fix path always raised AttributeError.
        """
        self.win.dir_name = self.temp_dir
        self.win._apply_label_fix('old', 'new')  # must not raise

    def test_reset_all_relaunches_with_python_interpreter(self):
        """reset_all must relaunch through sys.executable, not exec the .py.

        Regression: startDetached(os.path.abspath(__file__)) does not restart
        an installed (entry-point) package.
        """
        from unittest.mock import patch
        with patch.object(self.win, 'close'), \
                patch.object(self.win.settings, 'reset'), \
                patch('labelImgPlusPlus.QProcess') as mock_proc:
            instance = mock_proc.return_value
            self.win.reset_all()

        instance.startDetached.assert_called_once()
        args = instance.startDetached.call_args[0]
        self.assertEqual(args[0], sys.executable)

    def test_load_predefined_classes_none_does_not_raise(self):
        """load_predefined_classes(None) must no-op, not raise TypeError.

        The MainWindow constructor permits a None class file; the loader
        must tolerate it instead of passing None into os.path.exists.
        """
        self.win.load_predefined_classes(None)

    def test_get_labels_for_image_reads_createml(self):
        """_get_labels_for_image must read labels from a CreateML JSON.

        Regression: CreateMLReader was called with a single argument though
        its constructor needs two, raising a TypeError that a bare except
        swallowed - so the CreateML branch could never return any labels.
        """
        import json

        work_dir = tempfile.mkdtemp()
        try:
            img_path = os.path.join(work_dir, 'pic.png')
            img = QImage(80, 60, QImage.Format_RGB32)
            img.fill(0xFFFFFF)
            img.save(img_path)

            with open(os.path.join(work_dir, 'pic.json'), 'w') as f:
                json.dump([{
                    'image': 'pic.png',
                    'verified': False,
                    'annotations': [{
                        'label': 'cat',
                        'coordinates': {'x': 40, 'y': 30,
                                        'width': 20, 'height': 20},
                    }],
                }], f)

            self.assertIn('cat', self.win._get_labels_for_image(img_path))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def test_dirty_flag_on_annotation(self):
        """Test that dirty flag is set when adding annotation."""
        self.win.load_file(self.test_image_path)
        self.win.set_clean()
        self.assertFalse(self.win.dirty)

        # Simulate adding annotation via set_dirty
        self.win.set_dirty()

        self.assertTrue(self.win.dirty)

    def test_save_file_voc_format(self):
        """Test saving in PASCAL VOC format."""
        self.win.load_file(self.test_image_path)

        # Add annotation
        shape = Shape(label='car')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(50, 50))
        shape.close()
        self.win.add_label(shape)

        # Save as VOC
        from libs.formats.labelFile import LabelFileFormat
        self.win.label_file_format = LabelFileFormat.PASCAL_VOC
        self.win.save_file()

        # Check XML file exists
        xml_path = os.path.join(self.temp_dir, 'test_image.xml')
        self.assertTrue(os.path.exists(xml_path))

    def test_save_file_yolo_format(self):
        """Test saving in YOLO format."""
        self.win.load_file(self.test_image_path)

        # Add annotation
        shape = Shape(label='car')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(50, 50))
        shape.close()
        self.win.add_label(shape)

        # Save as YOLO
        from libs.formats.labelFile import LabelFileFormat
        self.win.label_file_format = LabelFileFormat.YOLO
        self.win.save_file()

        # Check TXT file exists
        txt_path = os.path.join(self.temp_dir, 'test_image.txt')
        self.assertTrue(os.path.exists(txt_path))


class TestMainWindowNavigation(unittest.TestCase):
    """Tests for image navigation."""

    @classmethod
    def setUpClass(cls):
        """Create app and test images."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()

        # Create multiple test images
        cls.image_paths = []
        for i in range(3):
            path = os.path.join(cls.temp_dir, f'image_{i}.png')
            img = QImage(100, 100, QImage.Format_RGB32)
            img.fill(0xFFFFFF)
            img.save(path)
            cls.image_paths.append(path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Load directory before each test."""
        self.win.reset_state()
        self.win.import_dir_images(self.temp_dir)
        self.win.load_file(self.image_paths[0])

    def test_next_image(self):
        """Test navigating to next image."""
        initial_path = self.win.file_path
        self.win.open_next_image()
        self.assertNotEqual(self.win.file_path, initial_path)
        self.assertEqual(self.win.file_path, self.image_paths[1])

    def test_prev_image(self):
        """Test navigating to previous image."""
        # Start from second image
        self.win.load_file(self.image_paths[1])
        initial_path = self.win.file_path
        self.win.open_prev_image()
        # Should have moved to a different image (or stayed if at start)
        # Just verify navigation doesn't crash
        self.assertIsNotNone(self.win.file_path)

    def test_navigation_at_end(self):
        """Test navigation at end of list."""
        # Go to last image
        self.win.load_file(self.image_paths[-1])
        self.win.open_next_image()
        # Should stay at last or wrap - check doesn't crash
        self.assertIsNotNone(self.win.file_path)

    def test_navigation_at_start(self):
        """Test navigation at start of list."""
        self.win.load_file(self.image_paths[0])
        self.win.open_prev_image()
        # Should stay at first or wrap - check doesn't crash
        self.assertIsNotNone(self.win.file_path)

    def test_image_list_populated(self):
        """Test that image list is populated correctly."""
        self.assertEqual(len(self.win.m_img_list), 3)


class TestMainWindowAnnotations(unittest.TestCase):
    """Tests for annotation operations."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset and load test image."""
        self.win.reset_state()
        self.win.load_file(self.test_image_path)

    def test_create_shape(self):
        """Test creating a bounding box annotation."""
        shape = Shape(label='person')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(60, 60))
        shape.close()

        # Add to canvas directly (like the canvas test pattern)
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 1)
        self.assertEqual(self.win.canvas.shapes[0].label, 'person')

    def test_delete_shape(self):
        """Test deleting an annotation."""
        # Add shape
        shape = Shape(label='person')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(60, 60))
        shape.close()
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 1)

        # Remove shape
        self.win.canvas.shapes.remove(shape)
        self.win.remove_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 0)

    def test_multiple_shapes(self):
        """Test handling multiple annotations."""
        for i, label in enumerate(['car', 'person', 'bike']):
            shape = Shape(label=label)
            shape.add_point(QPointF(10 + i*20, 10))
            shape.add_point(QPointF(50 + i*20, 50))
            shape.close()
            self.win.canvas.shapes.append(shape)
            self.win.add_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 3)


class TestMainWindowModes(unittest.TestCase):
    """Tests for mode switching."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        # Create test image for zoom tests
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_toggle_advanced_mode(self):
        """Test switching to advanced mode."""
        # Start in beginner mode
        self.assertTrue(self.win.beginner())

        self.win.toggle_advanced_mode(True)

        self.assertFalse(self.win.beginner())

    def test_toggle_beginner_mode(self):
        """Test switching back to beginner mode."""
        self.win.toggle_advanced_mode(True)
        self.assertFalse(self.win.beginner())

        self.win.toggle_advanced_mode(False)

        self.assertTrue(self.win.beginner())

    def test_zoom_in(self):
        """Test zoom in operation."""
        self.win.load_file(self.test_image_path)
        self.win.set_zoom(100)
        initial_zoom = self.win.zoom_widget.value()
        self.win.add_zoom(10)
        self.assertGreater(self.win.zoom_widget.value(), initial_zoom)

    def test_zoom_out(self):
        """Test zoom out operation."""
        self.win.load_file(self.test_image_path)
        self.win.set_zoom(150)
        initial_zoom = self.win.zoom_widget.value()
        self.win.add_zoom(-10)
        self.assertLess(self.win.zoom_widget.value(), initial_zoom)


class TestMainWindowLoaderFormatPreservation(unittest.TestCase):
    """Tests that loader methods don't mutate label_file_format on reader failure."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset and load test image; silence error_message dialog."""
        self.win.reset_state()
        self.win.load_file(self.test_image_path)
        # Save and silence error_message so we don't pop dialogs in tests.
        self._orig_error_message = self.win.error_message
        self.win.error_message = lambda *a, **kw: None

    def tearDown(self):
        """Restore error_message."""
        self.win.error_message = self._orig_error_message

    def test_load_coco_json_does_not_change_format_on_reader_failure(self):
        """Reader failure must not leave label_file_format mutated."""
        from libs.formats.labelFile import LabelFileFormat

        bad_json = os.path.join(self.temp_dir, 'bad.json')
        with open(bad_json, 'w') as f:
            f.write('{ this is not valid json')

        self.win.label_file_format = LabelFileFormat.YOLO  # known start state
        self.win.load_coco_json_by_filename(bad_json, self.test_image_path)
        self.assertEqual(
            self.win.label_file_format, LabelFileFormat.YOLO,
            'format must not be mutated on reader failure')

    def test_load_yolo_seg_does_not_change_format_on_reader_failure(self):
        """Reader failure (missing classes.txt) must not mutate format."""
        from libs.formats.labelFile import LabelFileFormat

        # Valid YOLO-seg txt content but no classes.txt sibling -> reader raises.
        seg_dir = tempfile.mkdtemp()
        try:
            seg_txt = os.path.join(seg_dir, 'x.txt')
            with open(seg_txt, 'w') as f:
                f.write('0 0.1 0.1 0.2 0.1 0.2 0.2\n')

            self.win.label_file_format = LabelFileFormat.YOLO  # known start state
            self.win.load_yolo_seg_by_filename(seg_txt)
            self.assertEqual(
                self.win.label_file_format, LabelFileFormat.YOLO,
                'format must not be mutated on reader failure')
        finally:
            shutil.rmtree(seg_dir, ignore_errors=True)

    def test_load_create_ml_bad_json_does_not_raise(self):
        """A malformed CreateML JSON must be reported, not crash the load."""
        from libs.formats.labelFile import LabelFileFormat

        bad_json = os.path.join(self.temp_dir, 'bad_createml.json')
        with open(bad_json, 'w') as f:
            f.write('{ this is not valid json')

        self.win.label_file_format = LabelFileFormat.YOLO  # known start state
        # Must not raise - reader failure is caught and surfaced via dialog.
        self.win.load_create_ml_json_by_filename(bad_json, self.test_image_path)
        self.assertEqual(
            self.win.label_file_format, LabelFileFormat.YOLO,
            'format must not be mutated on reader failure')


class TestMainWindowPolygonKeypointUndo(unittest.TestCase):
    """Integration tests for polygon and keypoint undo support."""

    @classmethod
    def setUpClass(cls):
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset state and clear the undo stack for a clean test."""
        self.win.reset_state()
        self.win.load_file(self.test_image_path)
        self.win.undo_stack.clear()

    def test_polygon_vertex_edit_pushes_undoable_command(self):
        """polygonVerticesEdited -> pushes EditPolygonVerticesCommand,
        and undo restores the pre-mutation points list."""
        from libs.core.shape import ShapeType

        shape = Shape(label='polygon', shape_type=ShapeType.POLYGON)
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(50, 10))
        shape.add_point(QPointF(50, 50))
        shape.add_point(QPointF(10, 50))
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)
        self.win.canvas.selected_shape = shape

        old = [QPointF(p.x(), p.y()) for p in shape.points]

        # Mutate then emit (mirrors what canvas does at each mutation site).
        shape.remove_point(1)
        self.win.canvas.polygonVerticesEdited.emit(shape, old)

        self.assertTrue(self.win.undo_stack.can_undo())
        self.assertEqual(len(shape.points), 3)

        self.win.undo_stack.undo()

        self.assertEqual(len(shape.points), 4)
        for actual, expected in zip(shape.points, old):
            self.assertEqual(actual.x(), expected.x())
            self.assertEqual(actual.y(), expected.y())

    def test_keypoint_edit_pushes_undoable_command(self):
        """keypointsEdited -> pushes EditKeypointsCommand,
        and undo restores the pre-mutation keypoints list."""
        shape = Shape(label='person')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(60, 60))
        shape.close()
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)

        old = None  # no keypoints placed yet
        shape.keypoints = [(20.0, 20.0, 2), None, None]
        self.win.canvas.keypointsEdited.emit(shape, old)

        self.assertTrue(self.win.undo_stack.can_undo())
        self.win.undo_stack.undo()
        self.assertIsNone(shape.keypoints)

    def test_rectangle_move_pushes_undoable_command(self):
        """shapeMoveFinished -> pushes MoveShapeCommand, and undo restores the
        rectangle's original position.

        Regression: MoveShapeCommand was implemented, exported, imported and
        unit-tested, but never wired into the app. Whole-shape (and rectangle
        vertex) drags emitted shapeMoved -> set_dirty only, bypassing the undo
        stack, so Ctrl+Z could not revert a moved box.
        """
        from libs.core.commands import MoveShapeCommand

        shape = Shape(label='car')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(50, 50))
        shape.close()
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)
        self.win.canvas.selected_shape = shape

        old = [QPointF(p.x(), p.y()) for p in shape.points]

        # Simulate a completed body drag: the canvas moved the points, then
        # reports the finished move on mouse release.
        shape.move_by(QPointF(20, 0))
        self.win.canvas.shapeMoveFinished.emit(shape, old)

        self.assertTrue(self.win.undo_stack.can_undo())
        self.assertIsInstance(self.win.undo_stack._undo_stack[-1], MoveShapeCommand)
        self.assertEqual(shape.points[0].x(), 30)

        self.win.undo_stack.undo()

        self.assertEqual(shape.points[0].x(), 10)
        self.assertEqual(shape.points[1].x(), 50)


if __name__ == '__main__':
    unittest.main()
