# tests/formats/test_format_metadata.py
"""Tests for the annotation-format metadata registry.

Consolidates the format display data (identifier strings, LabelFileFormat
enum, menu titles, themed-icon names, file suffixes, and the change-format
cycle) that used to be spread across MainWindow.get_format_meta / set_format /
change_format.
"""
import os
import sys
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.formats import format_metadata as fm
from libs.formats.labelFile import LabelFileFormat
from libs.formats.pascal_voc_io import XML_EXT
from libs.formats.yolo_io import TXT_EXT
from libs.formats.create_ml_io import JSON_EXT
from libs.utils.constants import (
    FORMAT_PASCALVOC, FORMAT_YOLO, FORMAT_CREATEML, FORMAT_COCO, FORMAT_YOLO_SEG)


class TestByName(unittest.TestCase):

    def test_maps_each_identifier_to_meta(self):
        cases = [
            (FORMAT_PASCALVOC, LabelFileFormat.PASCAL_VOC, 'format_voc', XML_EXT),
            (FORMAT_YOLO, LabelFileFormat.YOLO, 'format_yolo', TXT_EXT),
            (FORMAT_CREATEML, LabelFileFormat.CREATE_ML, 'format_createml', JSON_EXT),
            (FORMAT_COCO, LabelFileFormat.COCO, 'format_createml', JSON_EXT),
            (FORMAT_YOLO_SEG, LabelFileFormat.YOLO_SEG, 'format_yolo', TXT_EXT),
        ]
        for name, enum, icon, suffix in cases:
            meta = fm.by_name(name)
            self.assertIsNotNone(meta, name)
            self.assertEqual(meta.name, name)
            self.assertEqual(meta.enum, enum)
            self.assertEqual(meta.icon, icon)
            self.assertEqual(meta.suffix, suffix)

    def test_unknown_name_returns_none(self):
        self.assertIsNone(fm.by_name('NOT_A_FORMAT'))


class TestMetaForEnum(unittest.TestCase):

    def test_menu_titles_and_icons(self):
        self.assertEqual(fm.meta_for_enum(LabelFileFormat.PASCAL_VOC).menu_title,
                         '&PascalVOC')
        self.assertEqual(fm.meta_for_enum(LabelFileFormat.YOLO).menu_title, '&YOLO')
        self.assertEqual(fm.meta_for_enum(LabelFileFormat.CREATE_ML).menu_title,
                         '&CreateML')
        self.assertEqual(fm.meta_for_enum(LabelFileFormat.COCO).menu_title, '&COCO')
        self.assertEqual(fm.meta_for_enum(LabelFileFormat.YOLO_SEG).menu_title,
                         '&YOLO-seg')

    def test_unknown_enum_falls_back_to_pascal_voc(self):
        meta = fm.meta_for_enum(None)
        self.assertEqual(meta.enum, LabelFileFormat.PASCAL_VOC)
        self.assertEqual(meta.menu_title, '&PascalVOC')


class TestCycle(unittest.TestCase):

    def test_cycle_order_and_warnings(self):
        nxt, warn = fm.next_in_cycle(LabelFileFormat.PASCAL_VOC)
        self.assertEqual(nxt, FORMAT_YOLO)
        self.assertIn('difficult', warn)

        self.assertEqual(fm.next_in_cycle(LabelFileFormat.YOLO)[0], FORMAT_CREATEML)
        self.assertEqual(fm.next_in_cycle(LabelFileFormat.CREATE_ML)[0], FORMAT_COCO)
        self.assertEqual(fm.next_in_cycle(LabelFileFormat.COCO)[0], FORMAT_YOLO_SEG)
        self.assertEqual(fm.next_in_cycle(LabelFileFormat.YOLO_SEG)[0],
                         FORMAT_PASCALVOC)

    def test_full_cycle_returns_to_start(self):
        enum = LabelFileFormat.PASCAL_VOC
        seen = [enum]
        for _ in range(5):
            name, _w = fm.next_in_cycle(enum)
            enum = fm.by_name(name).enum
            seen.append(enum)
        self.assertEqual(seen[0], seen[-1])  # back to PASCAL_VOC after 5 hops
        self.assertEqual(len(set(seen[:-1])), 5)  # all five visited once

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            fm.next_in_cycle(None)


if __name__ == '__main__':
    unittest.main()
