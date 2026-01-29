"""Tests for Gallery mode logic (parsing, file lookup, caching)."""
import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', '..', 'libs')
sys.path.insert(0, libs_path)
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.galleryWidget import (
    find_annotation_file,
    parse_yolo_annotations,
    parse_voc_annotations,
    ThumbnailCache,
    AnnotationStatus,
)


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


class TestAnnotationStatus(unittest.TestCase):
    """Test cases for AnnotationStatus enum."""

    def test_status_values(self):
        """Test that status enum has expected values."""
        self.assertEqual(AnnotationStatus.NO_LABELS, 0)
        self.assertEqual(AnnotationStatus.HAS_LABELS, 1)
        self.assertEqual(AnnotationStatus.VERIFIED, 2)


if __name__ == '__main__':
    unittest.main()
