"""Tests for Gallery mode logic (parsing, file lookup, caching)."""
import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', '..', 'libs')
sys.path.insert(0, libs_path)
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication

from libs.widgets.galleryWidget import (
    OverlayShape,
    POLYGON,
    RECTANGLE,
    find_annotation_file,
    parse_json_overlay_shapes,
    parse_yolo_annotations,
    parse_yolo_overlay_shapes,
    parse_voc_annotations,
    parse_voc_overlay_shapes,
    ThumbnailCache,
    ThumbnailLoaderWorker,
    AnnotationStatus,
    GalleryWidget,
)
from libs.formats.annotation_paths import annotation_output_base

app = QApplication.instance() or QApplication(sys.argv)


class TestFindAnnotationFile(unittest.TestCase):
    """Test cases for find_annotation_file function."""

    def setUp(self):
        """Create temp directory structure for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.img_dir = os.path.join(self.temp_dir, 'images')
        self.save_dir = os.path.join(self.temp_dir, 'labels')
        os.makedirs(self.img_dir)
        os.makedirs(self.save_dir)

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_yolo_in_same_dir(self):
        """Test finding YOLO annotation in same directory as image."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        txt_path = os.path.join(self.img_dir, 'test.txt')

        # Create dummy files
        open(img_path, 'w').close()
        open(txt_path, 'w').close()

        ann_path, ann_format, classes_path = find_annotation_file(img_path)

        self.assertEqual(ann_path, txt_path)
        self.assertEqual(ann_format, 'yolo')

    def test_find_voc_in_same_dir(self):
        """Test finding Pascal VOC annotation in same directory as image."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        xml_path = os.path.join(self.img_dir, 'test.xml')

        open(img_path, 'w').close()
        open(xml_path, 'w').close()

        ann_path, ann_format, _ = find_annotation_file(img_path)

        self.assertEqual(ann_path, xml_path)
        self.assertEqual(ann_format, 'voc')

    def test_find_annotation_in_save_dir(self):
        """Test finding annotation in separate save directory."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        txt_path = os.path.join(self.save_dir, 'test.txt')

        open(img_path, 'w').close()
        open(txt_path, 'w').close()

        ann_path, ann_format, _ = find_annotation_file(img_path, save_dir=self.save_dir)

        self.assertEqual(ann_path, txt_path)
        self.assertEqual(ann_format, 'yolo')

    def test_yolo_preferred_over_voc(self):
        """Test that YOLO format is preferred when both exist."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        txt_path = os.path.join(self.img_dir, 'test.txt')
        xml_path = os.path.join(self.img_dir, 'test.xml')

        open(img_path, 'w').close()
        open(txt_path, 'w').close()
        open(xml_path, 'w').close()

        ann_path, ann_format, _ = find_annotation_file(img_path)

        self.assertEqual(ann_format, 'yolo')

    def test_no_annotation_found(self):
        """Test return values when no annotation exists."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        open(img_path, 'w').close()

        ann_path, ann_format, classes_path = find_annotation_file(img_path)

        self.assertIsNone(ann_path)
        self.assertIsNone(ann_format)

    def test_finds_classes_file(self):
        """Test that classes.txt is found alongside YOLO annotations."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        txt_path = os.path.join(self.img_dir, 'test.txt')
        classes_path = os.path.join(self.img_dir, 'classes.txt')

        open(img_path, 'w').close()
        open(txt_path, 'w').close()
        open(classes_path, 'w').close()

        _, _, found_classes = find_annotation_file(img_path)

        self.assertEqual(found_classes, classes_path)

    def test_collision_safe_yolo_precedes_stale_legacy_voc(self):
        """A target-specific annotation wins over a legacy basename decoy."""
        first_dir = os.path.join(self.img_dir, 'camera-a')
        second_dir = os.path.join(self.img_dir, 'camera-b')
        os.makedirs(first_dir)
        os.makedirs(second_dir)
        images = [
            os.path.join(first_dir, 'frame.jpg'),
            os.path.join(second_dir, 'frame.jpg'),
        ]
        for image_path in images:
            open(image_path, 'w').close()

        specific_txt = annotation_output_base(
            images[1], self.save_dir, images) + '.txt'
        legacy_xml = os.path.join(self.save_dir, 'frame.xml')
        classes_path = os.path.join(self.save_dir, 'classes.txt')
        open(specific_txt, 'w').close()
        open(legacy_xml, 'w').close()
        open(classes_path, 'w').close()

        result = find_annotation_file(
            images[1], save_dir=self.save_dir, image_list=images)

        self.assertEqual(result, (specific_txt, 'yolo', classes_path))

    def test_yolo_seg_detection_and_parent_classes_fallback(self):
        """Segmentation TXT is detected and can use parent classes.txt."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        txt_path = os.path.join(self.save_dir, 'test.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')
        open(img_path, 'w').close()
        with open(txt_path, 'w') as annotation_file:
            annotation_file.write('0 0.1 0.1 0.9 0.1 0.5 0.8\n')
        with open(classes_path, 'w') as classes_file:
            classes_file.write('triangle\n')

        result = find_annotation_file(img_path, save_dir=self.save_dir)

        self.assertEqual(result, (txt_path, 'yolo_seg', classes_path))

    def test_finds_shared_annotations_json(self):
        """Shared COCO annotations.json is considered after sidecars."""
        img_path = os.path.join(self.img_dir, 'test.jpg')
        shared_path = os.path.join(self.save_dir, 'annotations.json')
        open(img_path, 'w').close()
        with open(shared_path, 'w') as annotation_file:
            json.dump({'images': [], 'annotations': []}, annotation_file)

        result = find_annotation_file(img_path, save_dir=self.save_dir)

        self.assertEqual(result, (shared_path, 'coco', None))


class TestParseYoloAnnotations(unittest.TestCase):
    """Test cases for parse_yolo_annotations function."""

    def setUp(self):
        """Create temp directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_single_annotation(self):
        """Test parsing a single YOLO annotation."""
        txt_path = os.path.join(self.temp_dir, 'test.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("0 0.5 0.5 0.4 0.3\n")

        with open(classes_path, 'w') as f:
            f.write("person\n")

        annotations = parse_yolo_annotations(txt_path, classes_path)

        self.assertEqual(len(annotations), 1)
        label, bbox = annotations[0]
        self.assertEqual(label, 'person')
        self.assertEqual(bbox, (0.5, 0.5, 0.4, 0.3))

    def test_parse_multiple_annotations(self):
        """Test parsing multiple YOLO annotations."""
        txt_path = os.path.join(self.temp_dir, 'multi.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("0 0.2 0.2 0.1 0.1\n")
            f.write("1 0.8 0.8 0.2 0.2\n")

        with open(classes_path, 'w') as f:
            f.write("cat\ndog\n")

        annotations = parse_yolo_annotations(txt_path, classes_path)

        self.assertEqual(len(annotations), 2)
        self.assertEqual(annotations[0][0], 'cat')
        self.assertEqual(annotations[1][0], 'dog')

    def test_missing_classes_file_uses_fallback(self):
        """Test that missing classes file uses fallback label."""
        txt_path = os.path.join(self.temp_dir, 'test.txt')

        with open(txt_path, 'w') as f:
            f.write("5 0.5 0.5 0.3 0.3\n")

        annotations = parse_yolo_annotations(txt_path, None)

        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0][0], 'class_5')

    def test_nonexistent_file_returns_empty(self):
        """Test that nonexistent file returns empty list."""
        annotations = parse_yolo_annotations('/nonexistent/path.txt')
        self.assertEqual(annotations, [])

    def test_empty_file_returns_empty(self):
        """Test that empty file returns empty list."""
        txt_path = os.path.join(self.temp_dir, 'empty.txt')
        open(txt_path, 'w').close()

        annotations = parse_yolo_annotations(txt_path)
        self.assertEqual(annotations, [])


class TestParseVocAnnotations(unittest.TestCase):
    """Test cases for parse_voc_annotations function."""

    def setUp(self):
        """Create temp directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_single_object(self):
        """Test parsing a single VOC object."""
        xml_path = os.path.join(self.temp_dir, 'test.xml')

        xml_content = """<?xml version="1.0"?>
<annotation>
    <size>
        <width>100</width>
        <height>100</height>
        <depth>3</depth>
    </size>
    <object>
        <name>cat</name>
        <bndbox>
            <xmin>10</xmin>
            <ymin>20</ymin>
            <xmax>60</xmax>
            <ymax>80</ymax>
        </bndbox>
    </object>
</annotation>"""

        with open(xml_path, 'w') as f:
            f.write(xml_content)

        annotations = parse_voc_annotations(xml_path)

        self.assertEqual(len(annotations), 1)
        label, bbox = annotations[0]
        self.assertEqual(label, 'cat')

        # Check normalized coordinates
        x_center, y_center, w, h = bbox
        self.assertAlmostEqual(x_center, 0.35, places=2)  # (10+60)/2 / 100
        self.assertAlmostEqual(y_center, 0.5, places=2)   # (20+80)/2 / 100
        self.assertAlmostEqual(w, 0.5, places=2)          # (60-10) / 100
        self.assertAlmostEqual(h, 0.6, places=2)          # (80-20) / 100

    def test_parse_multiple_objects(self):
        """Test parsing multiple VOC objects."""
        xml_path = os.path.join(self.temp_dir, 'multi.xml')

        xml_content = """<?xml version="1.0"?>
<annotation>
    <size>
        <width>200</width>
        <height>200</height>
        <depth>3</depth>
    </size>
    <object>
        <name>dog</name>
        <bndbox>
            <xmin>0</xmin>
            <ymin>0</ymin>
            <xmax>100</xmax>
            <ymax>100</ymax>
        </bndbox>
    </object>
    <object>
        <name>cat</name>
        <bndbox>
            <xmin>100</xmin>
            <ymin>100</ymin>
            <xmax>200</xmax>
            <ymax>200</ymax>
        </bndbox>
    </object>
</annotation>"""

        with open(xml_path, 'w') as f:
            f.write(xml_content)

        annotations = parse_voc_annotations(xml_path)

        self.assertEqual(len(annotations), 2)
        labels = [ann[0] for ann in annotations]
        self.assertIn('dog', labels)
        self.assertIn('cat', labels)

    def test_nonexistent_file_returns_empty(self):
        """Test that nonexistent file returns empty list."""
        annotations = parse_voc_annotations('/nonexistent/path.xml')
        self.assertEqual(annotations, [])

    def test_missing_size_returns_empty(self):
        """Test that XML without size element returns empty list."""
        xml_path = os.path.join(self.temp_dir, 'nosize.xml')

        xml_content = """<?xml version="1.0"?>
<annotation>
    <object>
        <name>cat</name>
        <bndbox>
            <xmin>10</xmin>
            <ymin>20</ymin>
            <xmax>60</xmax>
            <ymax>80</ymax>
        </bndbox>
    </object>
</annotation>"""

        with open(xml_path, 'w') as f:
            f.write(xml_content)

        annotations = parse_voc_annotations(xml_path)
        self.assertEqual(annotations, [])


class TestOverlayParsers(unittest.TestCase):
    """Format readers produce one normalized shape representation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_yolo_seg_geometry_is_not_interpreted_as_a_bbox(self):
        txt_path = os.path.join(self.temp_dir, 'segmentation.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')
        with open(txt_path, 'w') as annotation_file:
            annotation_file.write(
                '0 0.10 0.20 0.80 0.20 0.55 0.90\n'
                '0 bad 0.2 0.8 0.2 0.5 0.9\n'
            )
        with open(classes_path, 'w') as classes_file:
            classes_file.write('object\n')

        legacy_boxes = parse_yolo_annotations(txt_path, classes_path)
        shapes = parse_yolo_overlay_shapes(txt_path, classes_path)

        self.assertEqual(legacy_boxes, [])
        self.assertEqual(shapes, [OverlayShape(
            'object', POLYGON,
            ((0.10, 0.20), (0.80, 0.20), (0.55, 0.90)),
        )])

    def test_voc_five_point_polygon_uses_original_image_dimensions(self):
        xml_path = os.path.join(self.temp_dir, 'polygon.xml')
        with open(xml_path, 'w') as annotation_file:
            annotation_file.write("""<?xml version="1.0"?>
<annotation>
  <filename>polygon.jpg</filename>
  <size><width>50</width><height>50</height><depth>3</depth></size>
  <object>
    <name>pentagon</name>
    <bndbox><xmin>20</xmin><ymin>10</ymin><xmax>120</xmax><ymax>80</ymax></bndbox>
    <polygon>
      <pt><x>20</x><y>10</y></pt>
      <pt><x>100</x><y>10</y></pt>
      <pt><x>120</x><y>50</y></pt>
      <pt><x>60</x><y>80</y></pt>
      <pt><x>20</x><y>50</y></pt>
    </polygon>
  </object>
</annotation>""")

        shapes = parse_voc_overlay_shapes(xml_path, QSize(200, 100))

        self.assertEqual(len(shapes), 1)
        self.assertEqual(shapes[0].shape_type, POLYGON)
        self.assertEqual(len(shapes[0].points), 5)
        self.assertEqual(shapes[0].points[0], (0.1, 0.1))
        self.assertEqual(shapes[0].points[2], (0.6, 0.5))

    def test_createml_selects_target_box(self):
        json_path = os.path.join(self.temp_dir, 'dataset.json')
        image_path = os.path.join(self.temp_dir, 'target.jpg')
        data = [
            {
                'image': 'other.jpg',
                'annotations': [{
                    'label': 'decoy',
                    'coordinates': {
                        'x': 10, 'y': 10, 'width': 5, 'height': 5,
                    },
                }],
            },
            {
                'image': 'target.jpg',
                'annotations': [{
                    'label': 'car',
                    'coordinates': {
                        'x': 100, 'y': 50, 'width': 40, 'height': 20,
                    },
                }],
            },
        ]
        with open(json_path, 'w') as annotation_file:
            json.dump(data, annotation_file)

        shapes = parse_json_overlay_shapes(
            json_path, image_path, QSize(200, 100))

        self.assertEqual(shapes, [OverlayShape(
            'car', RECTANGLE,
            ((0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)),
        )])

    def test_coco_selects_target_polygon_and_box_without_fallback(self):
        json_path = os.path.join(self.temp_dir, 'annotations.json')
        data = {
            'images': [
                {'id': 1, 'file_name': 'other.jpg',
                 'width': 200, 'height': 100},
                {'id': 2, 'file_name': 'target.jpg',
                 'width': 50, 'height': 50},
            ],
            'categories': [
                {'id': 1, 'name': 'region'},
                {'id': 2, 'name': 'vehicle'},
            ],
            'annotations': [
                {'id': 1, 'image_id': 1, 'category_id': 2,
                 'bbox': [0, 0, 200, 100]},
                {'id': 2, 'image_id': 2, 'category_id': 1,
                 'segmentation': [[20, 10, 100, 10, 60, 80]],
                 'bbox': [20, 10, 80, 70]},
                {'id': 3, 'image_id': 2, 'category_id': 2,
                 'bbox': [100, 20, 40, 30]},
            ],
        }
        with open(json_path, 'w') as annotation_file:
            json.dump(data, annotation_file)

        shapes = parse_json_overlay_shapes(
            json_path,
            os.path.join(self.temp_dir, 'target.jpg'),
            QSize(200, 100),
        )
        missing = parse_json_overlay_shapes(
            json_path,
            os.path.join(self.temp_dir, 'missing.jpg'),
            QSize(200, 100),
        )

        self.assertEqual([shape.shape_type for shape in shapes],
                         [POLYGON, RECTANGLE])
        self.assertEqual(shapes[0].points,
                         ((0.1, 0.1), (0.5, 0.1), (0.3, 0.8)))
        self.assertEqual(shapes[1].points,
                         ((0.5, 0.2), (0.7, 0.2),
                          (0.7, 0.5), (0.5, 0.5)))
        self.assertEqual(missing, [])

    def test_malformed_json_returns_no_shapes(self):
        json_path = os.path.join(self.temp_dir, 'broken.json')
        with open(json_path, 'w') as annotation_file:
            annotation_file.write('{not-json')

        self.assertEqual(parse_json_overlay_shapes(
            json_path, 'target.jpg', QSize(200, 100)), [])


class TestThumbnailCache(unittest.TestCase):
    """Test cases for ThumbnailCache LRU cache."""

    def test_put_and_get(self):
        """Test basic put and get operations."""
        cache = ThumbnailCache(max_size=10)

        cache.put('/path/img1.jpg', 'pixmap1')
        result = cache.get('/path/img1.jpg')

        self.assertEqual(result, 'pixmap1')

    def test_get_missing_returns_none(self):
        """Test that getting missing key returns None."""
        cache = ThumbnailCache()

        result = cache.get('/nonexistent/path.jpg')

        self.assertIsNone(result)

    def test_lru_eviction(self):
        """Test that oldest items are evicted when cache is full."""
        cache = ThumbnailCache(max_size=3)

        cache.put('/img1.jpg', 'p1')
        cache.put('/img2.jpg', 'p2')
        cache.put('/img3.jpg', 'p3')

        # Cache is full, adding another should evict img1
        cache.put('/img4.jpg', 'p4')

        self.assertIsNone(cache.get('/img1.jpg'))
        self.assertEqual(cache.get('/img2.jpg'), 'p2')
        self.assertEqual(cache.get('/img3.jpg'), 'p3')
        self.assertEqual(cache.get('/img4.jpg'), 'p4')

    def test_access_updates_recency(self):
        """Test that accessing an item updates its recency."""
        cache = ThumbnailCache(max_size=3)

        cache.put('/img1.jpg', 'p1')
        cache.put('/img2.jpg', 'p2')
        cache.put('/img3.jpg', 'p3')

        # Access img1 to make it most recent
        cache.get('/img1.jpg')

        # Add new item - should evict img2 (now oldest)
        cache.put('/img4.jpg', 'p4')

        self.assertEqual(cache.get('/img1.jpg'), 'p1')  # Still there
        self.assertIsNone(cache.get('/img2.jpg'))       # Evicted

    def test_clear(self):
        """Test clearing the cache."""
        cache = ThumbnailCache()

        cache.put('/img1.jpg', 'p1')
        cache.put('/img2.jpg', 'p2')

        cache.clear()

        self.assertIsNone(cache.get('/img1.jpg'))
        self.assertIsNone(cache.get('/img2.jpg'))

    def test_remove(self):
        """Test removing specific item from cache."""
        cache = ThumbnailCache()

        cache.put('/img1.jpg', 'p1')
        cache.put('/img2.jpg', 'p2')

        cache.remove('/img1.jpg')

        self.assertIsNone(cache.get('/img1.jpg'))
        self.assertEqual(cache.get('/img2.jpg'), 'p2')

    def test_remove_nonexistent_no_error(self):
        """Test that removing nonexistent item doesn't raise error."""
        cache = ThumbnailCache()

        # Should not raise
        cache.remove('/nonexistent.jpg')

    def test_update_existing_key(self):
        """Test that putting existing key updates value and recency."""
        cache = ThumbnailCache(max_size=3)

        cache.put('/img1.jpg', 'old_value')
        cache.put('/img2.jpg', 'p2')
        cache.put('/img3.jpg', 'p3')

        # Update img1
        cache.put('/img1.jpg', 'new_value')

        self.assertEqual(cache.get('/img1.jpg'), 'new_value')

        # img1 should now be most recent, so adding new item evicts img2
        cache.put('/img4.jpg', 'p4')

        self.assertEqual(cache.get('/img1.jpg'), 'new_value')
        self.assertIsNone(cache.get('/img2.jpg'))

    def test_byte_limit_evicts_oldest_thumbnail(self):
        cache = ThumbnailCache(max_size=10, max_bytes=8 * 8 * 4)
        first_image = QImage(8, 8, QImage.Format_RGB32)
        first_image.fill(0xFFFF0000)
        second_image = QImage(8, 8, QImage.Format_RGB32)
        second_image.fill(0xFF00FF00)
        first = QPixmap.fromImage(first_image)
        second = QPixmap.fromImage(second_image)

        cache.put('/img1.jpg', first)
        cache.put('/img2.jpg', second)

        self.assertIsNone(cache.get('/img1.jpg'))
        self.assertIsNotNone(cache.get('/img2.jpg'))
        self.assertLessEqual(cache.bytes_used, cache.max_bytes)


class TestAnnotationStatus(unittest.TestCase):
    """Test cases for AnnotationStatus enum."""

    def test_status_values(self):
        """Test that status enum has expected values."""
        self.assertEqual(AnnotationStatus.NO_LABELS, 0)
        self.assertEqual(AnnotationStatus.HAS_LABELS, 1)
        self.assertEqual(AnnotationStatus.VERIFIED, 2)


class TestThumbnailImageListPropagation(unittest.TestCase):
    """Thumbnail lookup must receive the complete gallery image list."""

    def test_worker_passes_image_list_to_annotation_lookup(self):
        image_list = ['/images/a/frame.jpg', '/images/b/frame.jpg']
        worker = ThumbnailLoaderWorker(
            image_list[0], save_dir='/labels', image_list=image_list)

        with patch(
            'libs.widgets.galleryWidget.find_annotation_file',
            return_value=(None, None, None),
        ) as find_annotation:
            worker._draw_annotations(QImage(10, 10, QImage.Format_RGB32))

        find_annotation.assert_called_once_with(
            image_list[0], '/labels', image_list)

    def test_gallery_passes_image_list_when_constructing_worker(self):
        gallery = GalleryWidget(show_size_slider=False)
        gallery._save_dir = '/labels'
        gallery._image_list = [
            '/images/a/frame.jpg', '/images/b/frame.jpg']
        gallery.thread_pool = MagicMock()

        with patch(
            'libs.widgets.galleryWidget.ThumbnailLoaderWorker'
        ) as worker_class:
            gallery._load_thumbnail_async(gallery._image_list[0])

        worker_class.assert_called_once_with(
            gallery._image_list[0], gallery._icon_size, '/labels',
            gallery._image_list)
        gallery.thread_pool.start.assert_called_once_with(
            worker_class.return_value)


class TestThumbnailRefresh(unittest.TestCase):
    """A refresh must supersede any older worker for the same image."""

    @staticmethod
    def _solid_image(rgb):
        image = QImage(8, 8, QImage.Format_RGB32)
        image.fill(rgb)
        return image

    def test_older_result_cannot_overwrite_refreshed_thumbnail(self):
        gallery = GalleryWidget(show_size_slider=False)
        image_path = '/images/target.jpg'
        gallery.thread_pool = MagicMock()
        old_worker = MagicMock()
        refreshed_worker = MagicMock()

        with patch(
            'libs.widgets.galleryWidget.ThumbnailLoaderWorker',
            side_effect=[old_worker, refreshed_worker],
        ):
            gallery._load_thumbnail_async(image_path)
            gallery.refresh_thumbnail(image_path)

        old_result = old_worker.signals.thumbnail_ready.connect.call_args[0][0]
        refreshed_result = (
            refreshed_worker.signals.thumbnail_ready.connect.call_args[0][0])
        refreshed_result(image_path, self._solid_image(0xFF00FF00))
        old_result(image_path, self._solid_image(0xFFFF0000))

        cached = gallery.thumbnail_cache.get(image_path).toImage()
        self.assertEqual(cached.pixel(0, 0) & 0x00FFFFFF, 0x0000FF00)

    def test_older_result_does_not_finish_refreshed_request(self):
        gallery = GalleryWidget(show_size_slider=False)
        image_path = '/images/target.jpg'
        gallery.thread_pool = MagicMock()
        old_worker = MagicMock()
        refreshed_worker = MagicMock()

        with patch(
            'libs.widgets.galleryWidget.ThumbnailLoaderWorker',
            side_effect=[old_worker, refreshed_worker],
        ):
            gallery._load_thumbnail_async(image_path)
            gallery.refresh_thumbnail(image_path)

        old_result = old_worker.signals.thumbnail_ready.connect.call_args[0][0]
        old_result(image_path, self._solid_image(0xFFFF0000))

        self.assertIn(image_path, gallery._loading_paths)
        self.assertIsNone(gallery.thumbnail_cache.get(image_path))

    def test_loaded_callback_without_request_id_remains_supported(self):
        gallery = GalleryWidget(show_size_slider=False)
        image_path = '/images/target.jpg'

        gallery._on_thumbnail_loaded(
            image_path, self._solid_image(0xFF0000FF))

        cached = gallery.thumbnail_cache.get(image_path).toImage()
        self.assertEqual(cached.pixel(0, 0) & 0x00FFFFFF, 0x000000FF)


class TestThumbnailOverlayDrawing(unittest.TestCase):
    """Thumbnail painting keeps rectangles and polygons distinct."""

    def test_draws_polygon_outline_and_rectangle_corner_markers(self):
        worker = ThumbnailLoaderWorker('/images/target.jpg')
        image = QImage(100, 100, QImage.Format_RGB32)
        shapes = [
            OverlayShape(
                'box', RECTANGLE,
                ((0.1, 0.1), (0.8, 0.1), (0.8, 0.8), (0.1, 0.8)),
            ),
            OverlayShape(
                'region', POLYGON,
                ((0.2, 0.2), (0.7, 0.3), (0.4, 0.9)),
            ),
        ]

        with patch(
            'libs.widgets.galleryWidget.find_annotation_file',
            return_value=('/labels/target.txt', 'yolo_seg', None),
        ), patch(
            'libs.widgets.galleryWidget.parse_overlay_annotations',
            return_value=shapes,
        ) as parse_annotations, patch(
            'libs.widgets.galleryWidget.QPainter',
        ) as painter_class:
            result = worker._draw_annotations(image, QSize(400, 200))

        self.assertIs(result, image)
        parse_annotations.assert_called_once_with(
            '/labels/target.txt',
            'yolo_seg',
            '/images/target.jpg',
            original_size=QSize(400, 200),
            classes_path=None,
        )
        painter = painter_class.return_value
        self.assertEqual(painter.drawLine.call_count, 8)
        painter.drawRect.assert_not_called()
        painter.drawPolygon.assert_called_once()
        painter.end.assert_called_once()

    def test_run_passes_unscaled_source_size_to_drawing(self):
        temp_dir = tempfile.mkdtemp()
        try:
            image_path = os.path.join(temp_dir, 'source.png')
            source = QImage(200, 100, QImage.Format_RGB32)
            self.assertTrue(source.save(image_path))
            worker = ThumbnailLoaderWorker(image_path, size=50)
            worker._draw_annotations = MagicMock(
                side_effect=lambda thumbnail, original_size: thumbnail)

            worker.run()

            thumbnail, original_size = worker._draw_annotations.call_args[0]
            self.assertEqual((thumbnail.width(), thumbnail.height()), (50, 25))
            self.assertEqual(
                (original_size.width(), original_size.height()), (200, 100))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_malformed_annotation_leaves_image_usable(self):
        temp_dir = tempfile.mkdtemp()
        try:
            image_path = os.path.join(temp_dir, 'target.jpg')
            json_path = os.path.join(temp_dir, 'target.json')
            open(image_path, 'w').close()
            with open(json_path, 'w') as annotation_file:
                annotation_file.write('[malformed')
            worker = ThumbnailLoaderWorker(image_path)
            image = QImage(20, 20, QImage.Format_RGB32)

            result = worker._draw_annotations(image, QSize(200, 100))

            self.assertIs(result, image)
            self.assertFalse(result.isNull())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestGalleryTheme(unittest.TestCase):
    """The gallery must theme itself regardless of the size slider."""

    def test_list_widget_themed_without_size_slider(self):
        """Without the size slider, the list widget must still be themed
        at construction (apply_theme must not be gated on the slider)."""
        gallery = GalleryWidget(show_size_slider=False)
        self.assertNotEqual(gallery.list_widget.styleSheet().strip(), '')

    def test_status_colors_match_dark_palette(self):
        """Status border colors must follow the active theme."""
        from libs.utils.styles import Theme, get_theme_colors, hex_to_qcolor
        gallery = GalleryWidget(show_size_slider=False)
        gallery.apply_theme(Theme.DARK)
        expected = hex_to_qcolor(get_theme_colors(Theme.DARK)['status_verified'])
        self.assertEqual(gallery._status_colors[AnnotationStatus.VERIFIED], expected)


class TestBoundedThumbnailScheduling(unittest.TestCase):
    def test_visible_scheduler_never_returns_more_than_queue_cap(self):
        gallery = GalleryWidget(show_size_slider=False)
        gallery.resize(900, 600)
        for index in range(700):
            gallery._add_item('/images/image-%04d.jpg' % index)
        gallery.show()
        app.processEvents()

        visible = gallery._visible_items_with_margin()

        self.assertLessEqual(len(visible), 512)

    def test_unloaded_items_share_one_placeholder_pixmap(self):
        gallery = GalleryWidget(show_size_slider=False)
        gallery._add_item('/images/first.jpg')
        gallery._add_item('/images/second.jpg')

        first = gallery._path_to_item['/images/first.jpg'].icon().pixmap(100)
        second = gallery._path_to_item['/images/second.jpg'].icon().pixmap(100)

        self.assertEqual(first.cacheKey(), second.cacheKey())


class TestGalleryStatusFilter(unittest.TestCase):
    """Gallery filtering follows the status combo's four-index contract."""

    def setUp(self):
        self.gallery = GalleryWidget(show_size_slider=False)
        self.paths = [
            '/images/unannotated.jpg',
            '/images/annotated.jpg',
            '/images/verified.jpg',
            '/images/pending.jpg',
        ]
        self.gallery.set_image_list(self.paths)
        self.gallery.update_all_statuses({
            self.paths[0]: AnnotationStatus.NO_LABELS,
            self.paths[1]: AnnotationStatus.HAS_LABELS,
            self.paths[2]: AnnotationStatus.VERIFIED,
        })

    def _visible_paths(self):
        return {
            path for path, item in self.gallery._path_to_item.items()
            if not item.isHidden()
        }

    def test_all_filter_includes_known_and_unknown_statuses(self):
        self.gallery.set_status_filter(0)
        self.assertEqual(self._visible_paths(), set(self.paths))

    def test_annotated_filter_includes_verified_and_hides_unknown(self):
        self.gallery.set_status_filter(1)
        self.assertEqual(self._visible_paths(), set(self.paths[1:3]))

    def test_verified_filter_only_includes_verified(self):
        self.gallery.set_status_filter(2)
        self.assertEqual(self._visible_paths(), {self.paths[2]})

    def test_unannotated_filter_only_includes_no_labels(self):
        self.gallery.set_status_filter(3)
        self.assertEqual(self._visible_paths(), {self.paths[0]})

    def test_async_status_arrival_re_evaluates_visibility(self):
        self.gallery.set_status_filter(1)
        self.assertNotIn(self.paths[3], self._visible_paths())

        self.gallery.update_status(
            self.paths[3], AnnotationStatus.HAS_LABELS)

        self.assertIn(self.paths[3], self._visible_paths())

    def test_status_change_after_save_or_verify_re_evaluates_visibility(self):
        self.gallery.set_status_filter(3)
        self.assertIn(self.paths[0], self._visible_paths())

        self.gallery.update_status(
            self.paths[0], AnnotationStatus.HAS_LABELS)
        self.assertNotIn(self.paths[0], self._visible_paths())

        self.gallery.set_status_filter(2)
        self.gallery.update_status(
            self.paths[0], AnnotationStatus.VERIFIED)
        self.assertIn(self.paths[0], self._visible_paths())

    def test_filter_survives_image_list_reload(self):
        self.gallery.set_status_filter(2)

        self.gallery.set_image_list(self.paths)
        self.assertEqual(self.gallery._status_filter, 2)
        self.assertEqual(self._visible_paths(), set())

        self.gallery.update_all_statuses({
            self.paths[0]: AnnotationStatus.NO_LABELS,
            self.paths[1]: AnnotationStatus.HAS_LABELS,
            self.paths[2]: AnnotationStatus.VERIFIED,
        })
        self.assertEqual(self._visible_paths(), {self.paths[2]})

    def test_rejects_unknown_filter_index(self):
        with self.assertRaises(ValueError):
            self.gallery.set_status_filter(4)


class TestOverlayColourMatchesCanvas(unittest.TestCase):
    """Gallery overlays and canvas shapes must agree on a label's colour.

    These were two independent hashes: the same label was drawn one colour on
    the canvas and a different one on its thumbnail. Only the presentation may
    differ -- a 2px thumbnail outline needs full alpha and a legible value,
    where the canvas fill wants alpha 100 and can afford to be dark.
    """

    LABELS = ('car', 'person', 'dog', 'traffic light', 'bicycle', 'bus')

    def test_hue_is_identical_to_the_canvas_colour(self):
        from libs.utils.utils import generate_color_by_text
        from libs.widgets.galleryWidget import overlay_color

        for label in self.LABELS:
            self.assertEqual(
                overlay_color(label).hue(),
                generate_color_by_text(label).hue(),
                'hue diverged from the canvas for %r' % label)

    def test_overlay_is_opaque_and_legible_on_a_thumbnail(self):
        from libs.widgets.galleryWidget import overlay_color

        for label in self.LABELS:
            colour = overlay_color(label)
            self.assertEqual(colour.alpha(), 255)
            self.assertGreaterEqual(colour.value(), 180)

    def test_distinct_labels_stay_distinguishable(self):
        from libs.widgets.galleryWidget import overlay_color

        names = {overlay_color(label).name() for label in self.LABELS}
        self.assertEqual(len(names), len(self.LABELS))


if __name__ == '__main__':
    unittest.main()
