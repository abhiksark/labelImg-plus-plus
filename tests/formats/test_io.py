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


if __name__ == '__main__':
    unittest.main()
