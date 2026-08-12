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

from PyQt5.QtCore import QPointF, Qt, QEvent  # noqa: E402
from PyQt5.QtGui import QImage, QMouseEvent  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QMessageBox, QToolButton  # noqa: E402

from labelImgPlusPlus import get_main_app  # noqa: E402
from libs.core.shape import Shape  # noqa: E402
from libs.formats.annotation_paths import annotation_output_base  # noqa: E402


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

    def _create_test_image(self, filename):
        path = os.path.join(self.temp_dir, filename)
        image = QImage(100, 100, QImage.Format_RGB32)
        image.fill(0xFFFFFF)
        self.assertTrue(image.save(path))
        return path

    def test_load_file_valid_image(self):
        """Test loading a valid image file."""
        self.win.load_file(self.test_image_path)
        self.assertEqual(self.win.file_path, self.test_image_path)
        self.assertFalse(self.win.image.isNull())

    def test_change_icon_size_auto_mode_does_not_raise(self):
        """Selecting 'Auto' icon size must not crash.

        Regression: the auto branch imported calculate_icon_size from the
        non-existent module path `libs.toolBar` (it lives in
        `libs.widgets.toolBar`), raising ModuleNotFoundError. sender() is
        patched to a fake Auto action (data() == 0) and the slot is called
        directly so any exception propagates.
        """
        from unittest.mock import MagicMock, patch
        fake_action = MagicMock()
        fake_action.data.return_value = 0  # 0 == Auto
        with patch.object(self.win, 'sender', return_value=fake_action):
            self.win.change_icon_size()  # must not raise

    def test_apply_theme_without_scroll_area_does_not_raise(self):
        """_apply_theme must not NameError when scroll_area is absent.

        Regression: `colors` was only bound inside the scroll_area block but
        referenced later in the save-status refresh.
        """
        saved = self.win.scroll_area
        self.win.scroll_area = None
        try:
            self.win._apply_theme(self.win._current_theme)  # must not raise
        finally:
            self.win.scroll_area = saved

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

    def test_apply_label_fix_explicitly_reports_not_applied(self):
        """The compatibility hook must not imply annotations were changed."""
        from unittest.mock import patch

        self.win.dir_name = self.temp_dir
        with patch.object(self.win.statusBar(), 'showMessage') as show_message, \
                patch('builtins.print') as print_message:
            result = self.win._apply_label_fix('old', 'new')

        self.assertFalse(result)
        show_message.assert_not_called()
        print_message.assert_not_called()

    def test_label_checker_does_not_wire_unavailable_fix_signal(self):
        """Opening the checker must not wire its unavailable fix signal."""
        from unittest.mock import patch

        self.win.dir_name = self.temp_dir
        with patch('labelImgPlusPlus.LabelCheckerDialog') as dialog_class:
            dialog = dialog_class.return_value
            self.win.check_label_consistency()

        dialog.fix_requested.connect.assert_not_called()
        dialog.exec_.assert_called_once_with()

    def test_reset_all_relaunches_with_python_interpreter(self):
        """reset_all must relaunch through sys.executable, not exec the .py.

        Regression: startDetached(os.path.abspath(__file__)) does not restart
        an installed (entry-point) package.
        """
        from unittest.mock import patch
        with patch.object(self.win, 'may_continue', return_value=True), \
                patch.object(self.win, 'close', return_value=True), \
                patch.object(self.win.settings, 'reset'), \
                patch('labelImgPlusPlus.QMessageBox.warning',
                      return_value=QMessageBox.Yes), \
                patch('labelImgPlusPlus.QProcess') as mock_proc:
            instance = mock_proc.return_value
            self.assertTrue(self.win.reset_all())

        instance.startDetached.assert_called_once()
        args = instance.startDetached.call_args[0]
        self.assertEqual(args[0], sys.executable)

    def test_reset_all_declined_at_the_prompt_changes_nothing(self):
        """Reset All is destructive and one misclick from Close in the menu."""
        from unittest.mock import patch

        with patch.object(self.win, 'may_continue', return_value=True), \
                patch('labelImgPlusPlus.QMessageBox.warning',
                      return_value=QMessageBox.Cancel) as confirm, \
                patch.object(self.win.settings, 'reset') as reset, \
                patch.object(self.win, 'close') as close, \
                patch('labelImgPlusPlus.QProcess') as process:
            self.assertFalse(self.win.reset_all())

        confirm.assert_called_once()
        # Cancel must be the default button, so Enter cannot wipe settings.
        self.assertEqual(confirm.call_args.args[-1], QMessageBox.Cancel)
        reset.assert_not_called()
        close.assert_not_called()
        process.assert_not_called()

    def test_cancelled_close_returns_without_persisting_settings(self):
        """Cancelling an ordinary close must leave settings untouched."""
        from unittest.mock import MagicMock, patch

        event = MagicMock()
        settings = MagicMock()
        with patch.object(self.win, 'settings', settings), \
                patch.object(self.win, 'may_continue', return_value=False):
            self.win.closeEvent(event)

        event.ignore.assert_called_once_with()
        event.accept.assert_not_called()
        settings.__setitem__.assert_not_called()
        settings.save.assert_not_called()

    def test_cancelled_reset_keeps_window_and_settings(self):
        """Cancelling Reset All must not reset, close, or relaunch."""
        from unittest.mock import patch

        self.win.set_dirty()
        try:
            with patch.object(self.win, 'may_continue', return_value=False), \
                    patch.object(self.win.settings, 'reset') as reset, \
                    patch.object(self.win.settings, 'save') as save, \
                    patch.object(self.win, 'close') as close, \
                    patch('labelImgPlusPlus.QProcess') as process:
                self.assertFalse(self.win.reset_all())

            reset.assert_not_called()
            save.assert_not_called()
            close.assert_not_called()
            process.assert_not_called()
        finally:
            self.win.set_clean()

    def test_successful_reset_closes_without_resaving_settings(self):
        """An accepted reset clears settings and starts one replacement."""
        from unittest.mock import MagicMock, patch

        event = MagicMock()

        def close_window():
            self.win.closeEvent(event)
            return True

        self.win.set_dirty()
        try:
            with patch.object(self.win, 'may_continue', return_value=True) \
                    as may_continue, \
                    patch.object(self.win.settings, 'reset') as reset, \
                    patch.object(self.win.settings, 'save') as save, \
                    patch.object(self.win, 'close', side_effect=close_window) \
                    as close, \
                    patch('labelImgPlusPlus.QMessageBox.warning',
                          return_value=QMessageBox.Yes), \
                    patch('labelImgPlusPlus.QProcess') as process:
                self.assertTrue(self.win.reset_all())

            may_continue.assert_called_once_with()
            reset.assert_called_once_with()
            close.assert_called_once_with()
            event.accept.assert_called_once_with()
            event.ignore.assert_not_called()
            save.assert_not_called()
            process.assert_called_once_with()
            process.return_value.startDetached.assert_called_once_with(
                sys.executable, [os.path.abspath(os.path.join(
                    dir_name, '..', '..', 'labelImgPlusPlus.py'))])
        finally:
            self.win.set_clean()

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

    def test_delete_image_decline_keeps_current_image(self):
        """Declining the safe-default confirmation changes no state."""
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox

        self.win.load_file(self.test_image_path)
        with patch('labelImgPlusPlus.QMessageBox.warning',
                   return_value=QMessageBox.No) as confirm, \
                patch.object(self.win, 'may_continue') as may_continue, \
                patch('labelImgPlusPlus.os.remove') as remove, \
                patch.object(self.win, 'import_dir_images') as reload_images:
            self.assertFalse(self.win.delete_image())

        self.assertTrue(os.path.exists(self.test_image_path))
        self.assertEqual(self.win.file_path, self.test_image_path)
        self.assertEqual(confirm.call_args.args[-1], QMessageBox.No)
        may_continue.assert_not_called()
        remove.assert_not_called()
        reload_images.assert_not_called()

    def test_delete_image_dirty_cancel_keeps_current_image(self):
        """Cancelling dirty-state handling prevents removal and reload."""
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox

        self.win.load_file(self.test_image_path)
        self.win.set_dirty()
        with patch('labelImgPlusPlus.QMessageBox.warning',
                   return_value=QMessageBox.Yes), \
                patch.object(self.win, 'may_continue',
                             return_value=False) as may_continue, \
                patch('labelImgPlusPlus.os.remove') as remove, \
                patch.object(self.win, 'import_dir_images') as reload_images:
            self.assertFalse(self.win.delete_image())

        self.assertTrue(os.path.exists(self.test_image_path))
        self.assertEqual(self.win.file_path, self.test_image_path)
        self.assertTrue(self.win.dirty)
        may_continue.assert_called_once_with()
        remove.assert_not_called()
        reload_images.assert_not_called()

    def test_delete_image_success_clears_discarded_dirty_state(self):
        """A deleted dirty image cannot prompt again while reloading."""
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox

        delete_path = self._create_test_image('delete_success.png')
        self.win.set_clean()
        self.win.import_dir_images(self.temp_dir)
        self.win.cur_img_idx = self.win._path_to_idx[delete_path]
        self.win.load_file(delete_path)
        self.win.set_dirty()

        # Confirm deletion, then choose No in the unsaved-changes dialog to
        # discard edits. No third warning should appear during directory reload.
        with patch('labelImgPlusPlus.QMessageBox.warning',
                   side_effect=[QMessageBox.Yes, QMessageBox.No]) as warning:
            self.assertTrue(self.win.delete_image())

        self.assertFalse(os.path.exists(delete_path))
        self.assertFalse(self.win.dirty)
        self.assertNotEqual(self.win.file_path, delete_path)
        self.assertEqual(warning.call_count, 2)

    def test_delete_image_remove_failure_preserves_state(self):
        """Filesystem removal errors are reported without reloading state."""
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox

        self.win.load_file(self.test_image_path)
        self.win.set_dirty()
        with patch('labelImgPlusPlus.QMessageBox.warning',
                   return_value=QMessageBox.Yes), \
                patch.object(self.win, 'may_continue', return_value=True), \
                patch('labelImgPlusPlus.os.remove',
                      side_effect=OSError('permission denied')) as remove, \
                patch.object(self.win, 'error_message') as error_message, \
                patch.object(self.win, 'import_dir_images') as reload_images:
            self.assertFalse(self.win.delete_image())

        self.assertTrue(os.path.exists(self.test_image_path))
        self.assertEqual(self.win.file_path, self.test_image_path)
        self.assertTrue(self.win.dirty)
        remove.assert_called_once_with(self.test_image_path)
        error_message.assert_called_once()
        reload_images.assert_not_called()

    def test_may_continue_proceeds_after_successful_save(self):
        """Choosing Save permits navigation only when the save succeeds."""
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox

        self.win.set_dirty()
        with patch.object(self.win, 'discard_changes_dialog',
                          return_value=QMessageBox.Yes), \
                patch.object(self.win, 'save_file', return_value=True) as save:
            self.assertTrue(self.win.may_continue())

        save.assert_called_once_with()

    def test_may_continue_stays_when_save_fails(self):
        """Choosing Save must not discard edits when the save fails."""
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox

        self.win.set_dirty()
        with patch.object(self.win, 'discard_changes_dialog',
                          return_value=QMessageBox.Yes), \
                patch.object(self.win, 'save_file', return_value=False) as save:
            self.assertFalse(self.win.may_continue())

        save.assert_called_once_with()

    def test_first_save_without_save_dir_writes_beside_the_image(self):
        """No save directory means beside the image, never a dialog.

        Autosave is on by default and can fire from a timer or a navigation,
        so this path must never be able to raise a modal file chooser.
        """
        import os
        from unittest.mock import patch

        self.win.default_save_dir = None
        self.win.load_file(self.test_image_path)
        self.win.label_file = None
        self.win.set_dirty()

        expected = os.path.splitext(self.test_image_path)[0]
        with patch.object(self.win, 'save_file_dialog') as dialog, \
                patch.object(self.win, 'save_labels',
                             return_value=True) as save_labels:
            self.assertTrue(self.win.save_file())

        dialog.assert_not_called()
        save_labels.assert_called_once()
        written = save_labels.call_args[0][0]
        self.assertEqual(os.path.splitext(written)[0], expected)
        self.assertFalse(self.win.dirty)

    def test_save_file_propagates_label_save_failure(self):
        """A writer-reported failure leaves the window dirty."""
        from unittest.mock import patch

        self.win.load_file(self.test_image_path)
        self.win.set_dirty()

        with patch.object(self.win, 'save_labels', return_value=False):
            self.assertFalse(self.win.save_file())

        self.assertTrue(self.win.dirty)

    def test_successful_save_refreshes_every_live_gallery(self):
        """Persisted annotation changes invalidate both gallery thumbnails."""
        from unittest.mock import MagicMock, patch

        self.win.file_path = self.test_image_path
        full_gallery = MagicMock()
        status = object()
        with patch.object(self.win, 'save_labels', return_value=True), \
                patch.object(self.win, '_get_annotation_status',
                             return_value=status), \
                patch.object(self.win.gallery_widget,
                             'update_status') as dock_status, \
                patch.object(self.win.gallery_widget,
                             'refresh_thumbnail') as dock_refresh, \
                patch.object(self.win, 'full_gallery', full_gallery,
                             create=True):
            self.assertTrue(self.win._save_file('/labels/test_image'))

        dock_status.assert_called_once_with(self.test_image_path, status)
        dock_refresh.assert_called_once_with(self.test_image_path)
        full_gallery.update_status.assert_called_once_with(
            self.test_image_path, status)
        full_gallery.refresh_thumbnail.assert_called_once_with(
            self.test_image_path)

    def test_failed_save_does_not_refresh_any_gallery(self):
        """Cancelled or failed persistence must leave cached pixels alone."""
        from unittest.mock import MagicMock, patch

        self.win.file_path = self.test_image_path
        full_gallery = MagicMock()
        with patch.object(self.win, 'save_labels', return_value=False), \
                patch.object(self.win.gallery_widget,
                             'refresh_thumbnail') as dock_refresh, \
                patch.object(self.win, 'full_gallery', full_gallery,
                             create=True):
            self.assertFalse(self.win._save_file('/labels/test_image'))

        dock_refresh.assert_not_called()
        full_gallery.refresh_thumbnail.assert_not_called()

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
        self.win.set_dirty()
        self.assertTrue(self.win.save_file())
        self.assertFalse(self.win.dirty)

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


class TestRecursiveCentralAnnotationPaths(unittest.TestCase):
    """Central saves must not flatten recursive image collisions."""

    @classmethod
    def setUpClass(cls):
        cls.app, cls.win = get_main_app()

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.save_dir = os.path.join(self.root, 'annotations')
        os.makedirs(self.save_dir)

        self.images = []
        for directory in ('a', 'b'):
            image_dir = os.path.join(self.root, directory)
            os.makedirs(image_dir)
            image_path = os.path.join(image_dir, 'frame.png')
            image = QImage(100, 100, QImage.Format_RGB32)
            image.fill(0xFFFFFF)
            self.assertTrue(image.save(image_path))
            self.images.append(image_path)

        self.win.reset_state()
        self.win.default_save_dir = self.save_dir
        self.win.m_img_list = list(self.images)
        self.win._path_to_idx = {
            path: index for index, path in enumerate(self.images)
        }
        self.win.img_count = len(self.images)

    def tearDown(self):
        self.win.reset_state()
        shutil.rmtree(self.root, ignore_errors=True)

    def _save_voc_label(self, image_path, label):
        from libs.formats.labelFile import LabelFileFormat

        self.win.cur_img_idx = self.win._path_to_idx[image_path]
        self.assertTrue(self.win.load_file(image_path))
        shape = Shape(label=label)
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(50, 50))
        shape.close()
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)
        self.win.label_file_format = LabelFileFormat.PASCAL_VOC
        self.win.set_dirty()
        self.assertTrue(self.win.save_file())

    def test_colliding_recursive_images_save_and_reload_independently(self):
        from libs.formats.annotation_paths import annotation_output_base
        from libs.formats.annotation_probe import probe
        from libs.formats.pascal_voc_io import (
            PascalVocReader, PascalVocWriter,
        )

        expected_labels = {
            self.images[0]: 'alpha',
            self.images[1]: 'beta',
        }
        for image_path, label in expected_labels.items():
            self._save_voc_label(image_path, label)

        xml_paths = [
            annotation_output_base(
                image_path, self.save_dir, self.images) + '.xml'
            for image_path in self.images
        ]
        self.assertNotEqual(
            os.path.basename(xml_paths[0]).casefold(),
            os.path.basename(xml_paths[1]).casefold(),
        )
        self.assertNotIn(
            os.path.join(self.save_dir, 'frame.xml'), xml_paths)
        self.assertEqual(
            sorted(name for name in os.listdir(self.save_dir)
                   if name.endswith('.xml')),
            sorted(os.path.basename(path) for path in xml_paths),
        )

        for image_path, xml_path in zip(self.images, xml_paths):
            expected = expected_labels[image_path]
            self.assertTrue(os.path.isfile(xml_path))
            self.assertEqual(
                [shape[0] for shape in PascalVocReader(xml_path).get_shapes()],
                [expected],
            )

        # A stale legacy sidecar must not mask either image-specific file.
        legacy_writer = PascalVocWriter(
            'legacy', 'frame.png', (100, 100, 3))
        legacy_writer.add_bnd_box(
            1, 1, 20, 20, 'stale-legacy', difficult=0)
        legacy_writer.save(os.path.join(self.save_dir, 'frame.xml'))

        for image_path, xml_path in zip(self.images, xml_paths):
            expected = expected_labels[image_path]
            self.win.cur_img_idx = self.win._path_to_idx[image_path]
            self.assertTrue(self.win.load_file(image_path))
            self.assertEqual(
                [shape.label for shape in self.win.canvas.shapes],
                [expected],
            )

            info = probe(
                image_path, self.save_dir, want_labels=True,
                image_list=self.images)
            self.assertEqual(info.path, xml_path)
            self.assertEqual(info.labels, [expected])
            self.assertEqual(
                self.win._get_labels_for_image(image_path), [expected])

    def test_specific_txt_beats_stale_legacy_xml(self):
        from unittest.mock import patch

        from libs.formats.annotation_paths import annotation_output_base
        from libs.formats.labelFile import LabelFileFormat

        image_path = self.images[0]
        specific_txt = annotation_output_base(
            image_path, self.save_dir, self.images) + '.txt'
        with open(specific_txt, 'w') as annotation_file:
            annotation_file.write('')
        with open(os.path.join(self.save_dir, 'frame.xml'), 'w') \
                as legacy_file:
            legacy_file.write('<annotation/>')

        self.win.file_path = image_path
        for label_format, expected_loader, unexpected_loader in (
                (LabelFileFormat.YOLO,
                 'load_yolo_txt_by_filename',
                 'load_yolo_seg_by_filename'),
                (LabelFileFormat.YOLO_SEG,
                 'load_yolo_seg_by_filename',
                 'load_yolo_txt_by_filename')):
            with self.subTest(label_format=label_format), \
                    patch.object(self.win, expected_loader) as load_specific, \
                    patch.object(self.win, unexpected_loader) as load_other, \
                    patch.object(self.win,
                                 'load_pascal_xml_by_filename') as load_legacy:
                self.win.label_file_format = label_format
                self.win.show_bounding_box_from_annotation_file(image_path)

                load_specific.assert_called_once_with(specific_txt)
                load_other.assert_not_called()
                load_legacy.assert_not_called()

    def test_explicit_format_priority_within_specific_stem(self):
        from unittest.mock import patch

        from libs.formats.annotation_paths import annotation_output_base
        from libs.formats.labelFile import LabelFileFormat

        image_path = self.images[0]
        specific_base = annotation_output_base(
            image_path, self.save_dir, self.images)
        specific_xml = specific_base + '.xml'
        specific_txt = specific_base + '.txt'
        specific_json = specific_base + '.json'
        for annotation_path in (specific_xml, specific_txt, specific_json):
            with open(annotation_path, 'w') as annotation_file:
                annotation_file.write('')

        self.win.file_path = image_path
        self.win.label_file_format = LabelFileFormat.COCO
        with patch.object(self.win, 'load_coco_json_by_filename') \
                as load_coco, \
                patch.object(self.win, 'load_pascal_xml_by_filename') \
                as load_xml, \
                patch.object(self.win, 'load_yolo_txt_by_filename') \
                as load_yolo:
            self.win.show_bounding_box_from_annotation_file(image_path)

        load_coco.assert_called_once_with(specific_json, image_path)
        load_xml.assert_not_called()
        load_yolo.assert_not_called()

        self.win.label_file_format = LabelFileFormat.YOLO_SEG
        with patch.object(self.win, 'load_yolo_seg_by_filename') \
                as load_yolo_seg, \
                patch.object(self.win, 'load_pascal_xml_by_filename') \
                as load_xml, \
                patch.object(self.win, 'load_create_ml_json_by_filename') \
                as load_json:
            self.win.show_bounding_box_from_annotation_file(image_path)

        load_yolo_seg.assert_called_once_with(specific_txt)
        load_xml.assert_not_called()
        load_json.assert_not_called()


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

    def test_load_yolo_txt_does_not_change_format_on_reader_failure(self):
        """Missing classes.txt makes YoloReader raise; format must not flip
        and the load must not crash (Issue #69)."""
        from libs.formats.labelFile import LabelFileFormat

        # Valid YOLO txt but no classes.txt sibling -> reader raises.
        yolo_dir = tempfile.mkdtemp()
        try:
            yolo_txt = os.path.join(yolo_dir, 'x.txt')
            with open(yolo_txt, 'w') as f:
                f.write('0 0.5 0.5 0.5 0.5\n')

            # Start from a DIFFERENT format so a wrongful set_format is visible.
            self.win.label_file_format = LabelFileFormat.PASCAL_VOC
            self.win.load_yolo_txt_by_filename(yolo_txt)  # must not raise
            self.assertEqual(
                self.win.label_file_format, LabelFileFormat.PASCAL_VOC,
                'format must not be mutated on reader failure')
        finally:
            shutil.rmtree(yolo_dir, ignore_errors=True)

    def test_load_pascal_xml_does_not_change_format_on_reader_failure(self):
        """Malformed XML makes PascalVocReader raise; format must not flip
        and the load must not crash (Issue #69)."""
        from libs.formats.labelFile import LabelFileFormat

        bad_xml = os.path.join(self.temp_dir, 'bad.xml')
        with open(bad_xml, 'w') as f:
            f.write('<annotation><object><name>cat')  # truncated, invalid XML

        # Start from a DIFFERENT format so a wrongful set_format is visible.
        self.win.label_file_format = LabelFileFormat.YOLO
        self.win.load_pascal_xml_by_filename(bad_xml)  # must not raise
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

    def test_polygon_insert_then_drag_via_real_mouse_events_is_undoable(self):
        """End-to-end through real QMouseEvents (Issue #70).

        Pressing a polygon edge midpoint inserts a vertex; dragging it moves
        it; two undos restore the original geometry. This exercises the actual
        mousePress/Move/Release handlers, so a regression that severs the
        mouse-event -> edit-signal -> command wiring is caught — unlike the
        signal-level tests above, which emit the signals directly.
        """
        from libs.core.shape import ShapeType

        canvas = self.win.canvas
        canvas.mode = canvas.EDIT
        canvas.scale = 1.0

        shape = Shape(label='polygon', shape_type=ShapeType.POLYGON)
        for x, y in [(10, 10), (50, 10), (50, 50), (10, 50)]:
            shape.add_point(QPointF(x, y))
        canvas.shapes.append(shape)
        self.win.add_label(shape)
        canvas.selected_shape = shape
        self.win.undo_stack.clear()

        original = [(p.x(), p.y()) for p in shape.points]

        def evt(etype, x, y, button, buttons):
            # Map image-space -> widget-space (inverse of transform_pos).
            off = canvas.offset_to_center()
            wp = QPointF((x + off.x()) * canvas.scale,
                         (y + off.y()) * canvas.scale)
            return QMouseEvent(etype, wp, button, buttons, Qt.NoModifier)

        # 1. Press the midpoint of the top edge (10,10)-(50,10) -> insert vertex.
        canvas.mousePressEvent(
            evt(QEvent.MouseButtonPress, 30, 10,
                Qt.LeftButton, Qt.LeftButton))
        self.assertEqual(len(shape.points), 5,
                         'pressing an edge midpoint should insert a vertex')

        # 2. Drag the freshly inserted vertex down and release -> move.
        canvas.mouseMoveEvent(
            evt(QEvent.MouseMove, 30, 40, Qt.NoButton, Qt.LeftButton))
        canvas.mouseReleaseEvent(
            evt(QEvent.MouseButtonRelease, 30, 40,
                Qt.LeftButton, Qt.NoButton))

        # Both the insert and the drag-move must have pushed undo commands.
        self.assertEqual(len(self.win.undo_stack._undo_stack), 2,
                         'insert and drag-move should each push a command')

        # 3. Undo the move, then the insert -> back to the original 4 vertices.
        self.win.undo_stack.undo()
        self.win.undo_stack.undo()
        self.assertEqual([(p.x(), p.y()) for p in shape.points], original)


class TestUndoStateConsistency(unittest.TestCase):
    """Undo must restore label-list ordering and combo-box contents."""

    @classmethod
    def setUpClass(cls):
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        cls.img = os.path.join(cls.temp_dir, 'i.png')
        im = QImage(100, 100, QImage.Format_RGB32)
        im.fill(0xFFFFFF)
        im.save(cls.img)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        self.win.reset_state()
        self.win.load_file(self.img)
        self.win.undo_stack.clear()

    def _rect(self, label):
        s = Shape(label=label)
        s.add_point(QPointF(10, 10))
        s.add_point(QPointF(50, 50))
        s.close()
        return s

    def _combo_items(self):
        cb = self.win.combo_box.cb
        return [cb.itemText(i) for i in range(cb.count())]

    def test_delete_undo_restores_label_list_row(self):
        """Deleting a non-last shape then undoing must put its list item back
        at the same row, not append it to the bottom."""
        from libs.core.commands import DeleteShapeCommand
        a, b, c = self._rect('a'), self._rect('b'), self._rect('c')
        for s in (a, b, c):
            self.win.canvas.shapes.append(s)
            self.win.add_label(s)
        identity = self.win.annotation_model.identity_for_shape(b)
        self.assertEqual(
            self.win.annotation_model.index_for_identity(identity).row(), 1)

        cmd = DeleteShapeCommand(self.win, b, self.win.canvas.shapes.index(b))
        cmd.execute()
        self.win.undo_stack.push(cmd)
        self.win.undo_stack.undo()

        self.assertEqual(
            self.win.annotation_model.index_for_identity(identity).row(), 1)

    def test_edit_label_updates_combo_box(self):
        """Editing a label (and undoing) must refresh the label combo box."""
        from libs.core.commands import EditLabelCommand
        s = self._rect('cat')
        self.win.canvas.shapes.append(s)
        self.win.add_label(s)
        self.assertIn('cat', self._combo_items())

        cmd = EditLabelCommand(self.win, s, 'cat', 'dog')
        cmd.execute()
        self.win.undo_stack.push(cmd)
        self.assertIn('dog', self._combo_items())

        self.win.undo_stack.undo()
        self.assertIn('cat', self._combo_items())


class TestBatchVerify(unittest.TestCase):
    """Batch verify must report files it could not update, not swallow them."""

    @classmethod
    def setUpClass(cls):
        cls.app, cls.win = get_main_app()

    def setUp(self):
        from libs.formats.pascal_voc_io import PascalVocWriter
        self.win.reset_state()
        self.d = tempfile.mkdtemp()
        self.win.default_save_dir = self.d
        imgs = []
        for name in ('a', 'b'):
            img = os.path.join(self.d, name + '.png')
            im = QImage(50, 50, QImage.Format_RGB32)
            im.fill(0xFFFFFF)
            im.save(img)
            w = PascalVocWriter('f', name + '.png', (50, 50, 3))
            w.add_bnd_box(1, 1, 9, 9, 'cat', difficult=0)
            w.save(os.path.join(self.d, name + '.xml'))
            imgs.append(img)
        # An annotated image whose XML is corrupt -> must surface as a failure.
        cimg = os.path.join(self.d, 'c.png')
        im = QImage(50, 50, QImage.Format_RGB32)
        im.fill(0xFFFFFF)
        im.save(cimg)
        with open(os.path.join(self.d, 'c.xml'), 'w') as f:
            f.write('<annotation><object> not closed')
        imgs.append(cimg)
        self.win.m_img_list = imgs

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_reports_failures_instead_of_swallowing(self):
        count, failures = self.win._apply_batch_verify(True)
        self.assertEqual(count, 2)
        self.assertEqual(len(failures), 1)
        self.assertTrue(any('c.png' in f[0] for f in failures))

    def test_actually_writes_verified_flag(self):
        from libs.formats.pascal_voc_io import PascalVocReader
        self.win._apply_batch_verify(True)
        self.assertTrue(
            PascalVocReader(os.path.join(self.d, 'a.xml')).verified)

    def test_status_filter_is_applied_to_dock_and_full_galleries(self):
        from unittest.mock import MagicMock, patch

        full_gallery = MagicMock()
        with patch.object(
            self.win.gallery_widget, 'set_status_filter'
        ) as dock_filter, patch.object(
            self.win, 'full_gallery', full_gallery, create=True
        ):
            self.win.apply_status_filter(2)

        dock_filter.assert_called_once_with(2)
        full_gallery.set_status_filter.assert_called_once_with(2)

    def test_collision_safe_status_and_batch_ignore_stale_legacy_xml(self):
        """Filters and batch verify must target each same-stem annotation."""
        from libs.formats.pascal_voc_io import (
            PascalVocReader, PascalVocWriter,
        )

        image_paths = []
        for directory in ('camera-a', 'camera-b'):
            image_dir = os.path.join(self.d, directory)
            os.makedirs(image_dir)
            image_path = os.path.join(image_dir, 'frame.png')
            image = QImage(50, 50, QImage.Format_RGB32)
            image.fill(0xFFFFFF)
            self.assertTrue(image.save(image_path))
            image_paths.append(image_path)

        def write_voc(path, verified):
            writer = PascalVocWriter('f', 'frame.png', (50, 50, 3))
            writer.verified = verified
            writer.add_bnd_box(1, 1, 9, 9, 'cat', difficult=0)
            writer.save(path)

        first_xml = annotation_output_base(
            image_paths[0], self.d, image_paths) + '.xml'
        second_txt = annotation_output_base(
            image_paths[1], self.d, image_paths) + '.txt'
        legacy_xml = os.path.join(self.d, 'frame.xml')
        write_voc(first_xml, verified=True)
        with open(second_txt, 'w') as f:
            f.write('0 0.5 0.5 0.2 0.2\n')
        write_voc(legacy_xml, verified=True)

        self.win.m_img_list = image_paths
        self.win.file_list_widget.clear()
        self.win.file_list_widget.addItems(image_paths)

        self.win.apply_status_filter(1)
        self.assertFalse(self.win.file_list_widget.item(0).isHidden())
        self.assertFalse(self.win.file_list_widget.item(1).isHidden())

        self.win.apply_status_filter(2)
        self.assertFalse(self.win.file_list_widget.item(0).isHidden())
        self.assertTrue(self.win.file_list_widget.item(1).isHidden())

        count, failures = self.win._apply_batch_verify(False)

        self.assertEqual(count, 1)
        self.assertEqual(failures, [
            (image_paths[1], 'not a PASCAL VOC annotation')])
        self.assertFalse(PascalVocReader(first_xml).verified)
        self.assertTrue(PascalVocReader(legacy_xml).verified)


class TestMainWindowChromeScalesForHiDPI(unittest.TestCase):
    """The compact canvas/status chrome scales without fixed label floors."""

    @classmethod
    def setUpClass(cls):
        # Build the window once, under a pinned 2x factor. Keep app/win as
        # class attributes so the QApplication is not garbage-collected
        # mid-suite (a local binding would destroy it and segfault later
        # tests). This mirrors the other integration test classes.
        from unittest.mock import patch
        from libs.utils import dpi
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0):
            cls.app, cls.win = get_main_app()

    def test_slim_status_and_canvas_buttons_double_at_2x(self):
        self.assertEqual(self.win.workspace_pages.status_strip.height(), 48)
        button = self.win.workspace_pages.canvas_chrome.findChildren(
            QToolButton)[0]
        self.assertEqual(button.width(), 64)


class TestCanvasKeepsFocusForToolShortcuts(unittest.TestCase):
    """Tool shortcuts (W/P/S/K) only fire while the canvas holds focus.

    Qt hands modifier-less letters to the focused widget first, so a list or
    combo that keeps focus silently swallows them. These tests pin the paths
    that hand focus back -- and the one that deliberately does not.
    """

    @classmethod
    def setUpClass(cls):
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        cls.paths = []
        for index in range(2):
            path = os.path.join(cls.temp_dir, 'frame-%d.png' % index)
            image = QImage(80, 60, QImage.Format_RGB32)
            image.fill(0xFFFFFF)
            image.save(path)
            cls.paths.append(path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        self.win.reset_state()
        self.win.default_save_dir = self.temp_dir
        self.win.show()
        self.app.processEvents()

    def test_loading_an_image_leaves_focus_on_the_canvas(self):
        """The annotate-next-image loop depends on this refocus."""
        self.win.load_file(self.paths[0])
        self.app.processEvents()
        self.assertTrue(self.win.canvas.hasFocus())

    def test_clicking_a_shape_in_the_objects_list_returns_focus(self):
        self.win.load_file(self.paths[0])
        self.app.processEvents()

        self.win.workspace_pages.set_page('canvas')
        self.win.canvas.setEnabled(True)
        shape = Shape(label='person')
        for point in ((5, 5), (40, 5), (40, 40), (5, 40)):
            shape.add_point(QPointF(*point))
        shape.close()
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)
        self.app.processEvents()

        self.win.annotation_search.setFocus()
        self.app.processEvents()
        self.assertFalse(self.win.canvas.hasFocus())

        index = self.win.annotation_proxy.index(0, 0)
        self.win.label_list.clicked.emit(index)
        self.app.processEvents()
        self.assertTrue(self.win.canvas.hasFocus())

    def test_clicking_a_file_in_the_list_returns_focus_to_canvas(self):
        """A single click syncs selection without loading, so nothing else
        would hand focus back and W/P/S/K would stop firing."""
        self.win.load_file(self.paths[0])
        self.win.m_img_list = list(self.paths)
        self.win._path_to_idx = {
            path: index for index, path in enumerate(self.paths)}
        self.win.file_list_widget.clear()
        self.win.file_list_widget.addItems(self.paths)
        self.win.workspace_pages.set_page('canvas')
        self.win.canvas.setEnabled(True)
        self.app.processEvents()

        self.win.annotation_search.setFocus()
        self.app.processEvents()
        self.assertFalse(self.win.canvas.hasFocus())

        self.win.file_item_clicked(self.win.file_list_widget.item(1))
        self.app.processEvents()
        self.assertTrue(self.win.canvas.hasFocus())

    def test_dock_gallery_click_returns_focus_but_full_gallery_does_not(self):
        self.win.load_file(self.paths[0])
        self.win.m_img_list = list(self.paths)
        self.win._path_to_idx = {
            path: index for index, path in enumerate(self.paths)}
        self.win.workspace_pages.set_page('canvas')
        self.win.canvas.setEnabled(True)
        self.app.processEvents()

        self.win.annotation_search.setFocus()
        self.app.processEvents()
        self.win.gallery_image_selected(self.paths[1], source='dock')
        self.app.processEvents()
        self.assertTrue(self.win.canvas.hasFocus())

        # The full gallery owns the whole page; stealing focus to a canvas
        # the user cannot see would be wrong.
        self.win.annotation_search.setFocus()
        self.win.workspace_pages.set_page('gallery')
        self.app.processEvents()
        self.win.gallery_image_selected(self.paths[0], source='full')
        self.app.processEvents()
        self.assertFalse(self.win.canvas.hasFocus())
        self.win.workspace_pages.set_page('canvas')

    def test_typing_in_the_search_field_is_left_alone(self):
        """Letters must still reach the search box - that is text entry."""
        self.win.load_file(self.paths[0])
        self.win.workspace_pages.set_page('canvas')
        self.win.canvas.setEnabled(True)
        self.app.processEvents()

        self.win.annotation_search.clear()
        self.win.annotation_search.setFocus()
        QTest.keyClicks(self.win.annotation_search, 'wps')
        self.app.processEvents()
        self.assertEqual(self.win.annotation_search.text(), 'wps')
        self.assertTrue(self.win.annotation_search.hasFocus())

    def test_keyboard_navigation_of_the_objects_list_keeps_its_focus(self):
        """Regression: refocus is wired to `clicked`, not `selectionChanged`.

        Hooking selection would fire on arrow-key moves too and yank focus
        away mid-navigation.
        """
        self.win.load_file(self.paths[0])
        self.app.processEvents()
        for label in ('person', 'car'):
            shape = Shape(label=label)
            for point in ((5, 5), (40, 5), (40, 40), (5, 40)):
                shape.add_point(QPointF(*point))
            shape.close()
            self.win.canvas.shapes.append(shape)
            self.win.add_label(shape)
        self.app.processEvents()

        self.win.label_list.setFocus()
        self.win.label_list.setCurrentIndex(
            self.win.annotation_proxy.index(0, 0))
        self.app.processEvents()
        self.assertTrue(self.win.label_list.hasFocus())

        QTest.keyClick(self.win.label_list, Qt.Key_Down)
        self.app.processEvents()
        self.assertTrue(
            self.win.label_list.hasFocus(),
            'arrow-key navigation must not hand focus to the canvas')


if __name__ == '__main__':
    unittest.main()
