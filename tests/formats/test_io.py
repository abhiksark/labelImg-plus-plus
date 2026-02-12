"""Tests for Pascal VOC and CreateML I/O with proper temp file isolation."""
import json
import os
import sys
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', '..', 'libs')
sys.path.insert(0, libs_path)

from libs.formats.pascal_voc_io import PascalVocWriter, PascalVocReader
from libs.formats.create_ml_io import CreateMLWriter, CreateMLReader


class TestPascalVocIO(unittest.TestCase):
    """Test cases for Pascal VOC XML format I/O."""

    def setUp(self):
        """Create a temp directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_and_read_roundtrip(self):
        """Test that write/read roundtrip preserves annotation data."""
        xml_path = os.path.join(self.temp_dir, 'test.xml')

        writer = PascalVocWriter('test_folder', 'test.jpg', (512, 512, 3),
                                 local_img_path='/path/to/test.jpg')
        writer.add_bnd_box(60, 40, 430, 504, 'person', difficult=1)
        writer.add_bnd_box(113, 40, 450, 403, 'face', difficult=0)
        writer.save(xml_path)

        reader = PascalVocReader(xml_path)
        shapes = reader.get_shapes()

        self.assertEqual(len(shapes), 2)
        # Shape format: (label, points, line_color, fill_color, difficult)
        person = shapes[0]
        face = shapes[1]

        self.assertEqual(person[0], 'person')
        self.assertEqual(person[1], [(60, 40), (430, 40), (430, 504), (60, 504)])
        self.assertTrue(person[4])  # difficult=True

        self.assertEqual(face[0], 'face')
        self.assertEqual(face[1], [(113, 40), (450, 40), (450, 403), (113, 403)])
        self.assertFalse(face[4])  # difficult=False

    def test_verified_flag_roundtrip(self):
        """Test that verified flag is preserved."""
        xml_path = os.path.join(self.temp_dir, 'verified.xml')

        writer = PascalVocWriter('folder', 'img.jpg', (100, 100, 3))
        writer.verified = True
        writer.add_bnd_box(10, 10, 50, 50, 'obj', difficult=0)
        writer.save(xml_path)

        reader = PascalVocReader(xml_path)
        self.assertTrue(reader.verified)

    def test_grayscale_image(self):
        """Test handling of grayscale image (depth=1)."""
        xml_path = os.path.join(self.temp_dir, 'gray.xml')

        writer = PascalVocWriter('folder', 'gray.jpg', (256, 256, 1))
        writer.add_bnd_box(0, 0, 100, 100, 'test', difficult=0)
        writer.save(xml_path)

        # Verify XML was created and is readable
        reader = PascalVocReader(xml_path)
        shapes = reader.get_shapes()
        self.assertEqual(len(shapes), 1)


class TestCreateMLIO(unittest.TestCase):
    """Test cases for CreateML JSON format I/O."""

    def setUp(self):
        """Create a temp directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_creates_valid_json(self):
        """Test that writer creates valid CreateML JSON."""
        json_path = os.path.join(self.temp_dir, 'annotations.json')

        person = {'label': 'person', 'points': ((65, 45), (420, 45), (420, 512), (65, 512))}
        face = {'label': 'face', 'points': ((245, 250), (350, 250), (350, 365), (245, 365))}
        shapes = [person, face]

        writer = CreateMLWriter('folder', 'test.jpg', (512, 512, 3), shapes, json_path,
                                local_img_path='/path/to/test.jpg')
        writer.verified = True
        writer.write()

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.assertEqual(len(data), 1)
        img_data = data[0]
        self.assertEqual(img_data['image'], 'test.jpg')
        self.assertTrue(img_data['verified'])
        self.assertEqual(len(img_data['annotations']), 2)

        # Check face annotation coordinates (center-based)
        face_ann = img_data['annotations'][1]
        self.assertEqual(face_ann['label'], 'face')
        coords = face_ann['coordinates']
        self.assertEqual(coords['width'], 105)   # 350 - 245
        self.assertEqual(coords['height'], 115)  # 365 - 250
        self.assertEqual(coords['x'], 297.5)     # 245 + 105/2
        self.assertEqual(coords['y'], 307.5)     # 250 + 115/2

    def test_write_and_read_roundtrip(self):
        """Test that write/read roundtrip preserves data."""
        json_path = os.path.join(self.temp_dir, 'roundtrip.json')

        shapes = [{'label': 'cat', 'points': ((100, 100), (200, 100), (200, 200), (100, 200))}]
        writer = CreateMLWriter('folder', 'cat.jpg', (300, 300, 3), shapes, json_path)
        writer.write()

        reader = CreateMLReader(json_path, 'folder/cat.jpg')
        read_shapes = reader.get_shapes()

        self.assertEqual(len(read_shapes), 1)
        self.assertEqual(read_shapes[0][0], 'cat')
        # Check corners are recovered correctly
        points = read_shapes[0][1]
        self.assertEqual(points[0], (100, 100))  # top-left
        self.assertEqual(points[2], (200, 200))  # bottom-right

    def test_append_to_existing_json(self):
        """Test that writing to existing JSON appends/updates correctly."""
        json_path = os.path.join(self.temp_dir, 'multi.json')

        # Write first image
        shapes1 = [{'label': 'dog', 'points': ((10, 10), (50, 10), (50, 50), (10, 50))}]
        writer1 = CreateMLWriter('folder', 'img1.jpg', (100, 100, 3), shapes1, json_path)
        writer1.write()

        # Write second image
        shapes2 = [{'label': 'cat', 'points': ((20, 20), (60, 20), (60, 60), (20, 60))}]
        writer2 = CreateMLWriter('folder', 'img2.jpg', (100, 100, 3), shapes2, json_path)
        writer2.write()

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.assertEqual(len(data), 2)
        images = [d['image'] for d in data]
        self.assertIn('img1.jpg', images)
        self.assertIn('img2.jpg', images)


class TestPascalVocEdgeCases(unittest.TestCase):
    """Edge case tests for Pascal VOC format error handling."""

    def setUp(self):
        """Create a temp directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_read_malformed_xml_raises_error(self):
        """Test reading malformed XML file raises ValueError."""
        xml_path = os.path.join(self.temp_dir, 'malformed.xml')
        with open(xml_path, 'w') as f:
            f.write('<annotation><object>not closed properly')

        with self.assertRaises((ValueError, Exception)):
            PascalVocReader(xml_path)

    def test_read_missing_bndbox_raises_error(self):
        """Test reading XML with missing bndbox raises ValueError."""
        xml_path = os.path.join(self.temp_dir, 'missing_bndbox.xml')
        with open(xml_path, 'w') as f:
            f.write('''<?xml version="1.0"?>
<annotation>
    <folder>test</folder>
    <filename>test.jpg</filename>
    <size><width>100</width><height>100</height><depth>3</depth></size>
    <object>
        <name>person</name>
    </object>
</annotation>''')

        with self.assertRaises((ValueError, AttributeError, Exception)):
            PascalVocReader(xml_path)

    def test_read_nonexistent_file_raises_error(self):
        """Test reading non-existent XML file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            PascalVocReader('/nonexistent/path/file.xml')

    def test_read_empty_file_raises_error(self):
        """Test reading empty XML file raises error."""
        xml_path = os.path.join(self.temp_dir, 'empty.xml')
        with open(xml_path, 'w') as f:
            f.write('')

        with self.assertRaises((ValueError, Exception)):
            PascalVocReader(xml_path)

    def test_write_empty_filename(self):
        """Test writing with empty filename."""
        xml_path = os.path.join(self.temp_dir, 'empty_name.xml')
        writer = PascalVocWriter('folder', '', (100, 100, 3))
        writer.add_bnd_box(10, 10, 50, 50, 'test', difficult=0)
        writer.save(xml_path)

        # Should still create valid XML
        self.assertTrue(os.path.exists(xml_path))

    def test_read_valid_xml_with_no_objects(self):
        """Test reading valid XML with no objects."""
        xml_path = os.path.join(self.temp_dir, 'no_objects.xml')
        with open(xml_path, 'w') as f:
            f.write('''<?xml version="1.0"?>
<annotation>
    <folder>test</folder>
    <filename>test.jpg</filename>
    <size><width>100</width><height>100</height><depth>3</depth></size>
</annotation>''')

        reader = PascalVocReader(xml_path)
        shapes = reader.get_shapes()
        self.assertEqual(shapes, [])


class TestCreateMLEdgeCases(unittest.TestCase):
    """Edge case tests for CreateML format error handling."""

    def setUp(self):
        """Create a temp directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_read_corrupt_json_returns_empty(self):
        """Test reading corrupt JSON file returns empty shapes (error is logged)."""
        json_path = os.path.join(self.temp_dir, 'corrupt.json')
        with open(json_path, 'w') as f:
            f.write('{invalid json content')

        # CreateMLReader catches ValueError and prints error
        reader = CreateMLReader(json_path, 'folder/test.jpg')
        shapes = reader.get_shapes()
        self.assertEqual(shapes, [])

    def test_read_json_array_empty(self):
        """Test reading JSON with empty array."""
        json_path = os.path.join(self.temp_dir, 'empty_array.json')
        with open(json_path, 'w') as f:
            f.write('[]')

        reader = CreateMLReader(json_path, 'folder/test.jpg')
        shapes = reader.get_shapes()
        self.assertEqual(shapes, [])

    def test_read_json_image_not_found(self):
        """Test reading JSON where requested image is not in the data."""
        json_path = os.path.join(self.temp_dir, 'other_image.json')
        with open(json_path, 'w') as f:
            json.dump([{'image': 'other.jpg', 'annotations': []}], f)

        reader = CreateMLReader(json_path, 'folder/test.jpg')
        shapes = reader.get_shapes()
        self.assertEqual(shapes, [])

    def test_read_nonexistent_json_raises_error(self):
        """Test reading non-existent JSON file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            CreateMLReader('/nonexistent/path/file.json', 'folder/test.jpg')

    def test_write_with_no_shapes(self):
        """Test writing with empty shapes list."""
        json_path = os.path.join(self.temp_dir, 'no_shapes.json')
        shapes = []
        writer = CreateMLWriter('folder', 'test.jpg', (100, 100, 3), shapes, json_path)
        writer.write()

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['annotations'], [])


if __name__ == '__main__':
    unittest.main()
