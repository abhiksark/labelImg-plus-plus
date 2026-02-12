# tests/tools/test_label_checker.py
"""Tests for the label consistency checker."""

import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', '..', 'libs')
sys.path.insert(0, libs_path)
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.tools.label_checker import (
    LabelConsistencyChecker,
    LabelIssue,
    IssueType
)


class TestLabelConsistencyChecker(unittest.TestCase):
    """Test cases for LabelConsistencyChecker."""

    def setUp(self):
        """Set up test fixtures."""
        self.predefined = ['person', 'car', 'dog', 'cat', 'bicycle']
        self.checker = LabelConsistencyChecker(self.predefined)

    def test_exact_match_no_issues(self):
        """Test that exact matches don't produce issues."""
        labels = {'person': ['file1.txt'], 'car': ['file2.txt']}
        issues = self.checker.check_labels(labels)
        self.assertEqual(len(issues), 0)

    def test_case_mismatch_detected(self):
        """Test that case mismatches are detected."""
        labels = {'Person': ['file1.txt'], 'CAR': ['file2.txt']}
        issues = self.checker.check_labels(labels)

        self.assertEqual(len(issues), 2)
        self.assertTrue(all(i.issue_type == IssueType.CASE_MISMATCH for i in issues))

        # Check suggestions
        person_issue = next(i for i in issues if i.label == 'Person')
        self.assertEqual(person_issue.suggestion, 'person')

    def test_whitespace_detected(self):
        """Test that whitespace issues are detected."""
        labels = {'person ': ['file1.txt'], ' car': ['file2.txt']}
        issues = self.checker.check_labels(labels)

        whitespace_issues = [i for i in issues if i.issue_type == IssueType.WHITESPACE]
        self.assertEqual(len(whitespace_issues), 2)

    def test_typo_detected(self):
        """Test that typos are detected with fuzzy matching."""
        labels = {'persom': ['file1.txt'], 'caar': ['file2.txt']}
        issues = self.checker.check_labels(labels)

        typo_issues = [i for i in issues if i.issue_type == IssueType.TYPO]
        self.assertGreater(len(typo_issues), 0)

        # 'persom' should suggest 'person'
        persom_issue = next((i for i in issues if i.label == 'persom'), None)
        self.assertIsNotNone(persom_issue)
        self.assertEqual(persom_issue.suggestion, 'person')

    def test_undefined_label_detected(self):
        """Test that undefined labels are detected."""
        labels = {'airplane': ['file1.txt'], 'truck': ['file2.txt']}
        issues = self.checker.check_labels(labels)

        undefined_issues = [i for i in issues if i.issue_type == IssueType.UNDEFINED]
        self.assertEqual(len(undefined_issues), 2)

    def test_normalize_label(self):
        """Test label normalization."""
        self.assertEqual(self.checker.normalize_label('person'), 'person')
        self.assertEqual(self.checker.normalize_label('Person'), 'person')
        self.assertEqual(self.checker.normalize_label(' person '), 'person')
        self.assertEqual(self.checker.normalize_label('PERSON'), 'person')
        # Unknown label stays as-is (stripped)
        self.assertEqual(self.checker.normalize_label(' unknown '), 'unknown')

    def test_file_count_in_issues(self):
        """Test that file count is correctly reported."""
        labels = {'Person': ['f1.txt', 'f2.txt', 'f3.txt']}
        issues = self.checker.check_labels(labels)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].count, 3)
        self.assertEqual(len(issues[0].files), 3)

    def test_similarity_threshold(self):
        """Test custom similarity threshold."""
        # With high threshold, should not match
        strict_checker = LabelConsistencyChecker(self.predefined, similarity_threshold=0.95)
        labels = {'persom': ['file1.txt']}
        issues = strict_checker.check_labels(labels)

        # Should be undefined, not typo, because similarity is below threshold
        undefined_issues = [i for i in issues if i.issue_type == IssueType.UNDEFINED]
        self.assertGreater(len(undefined_issues), 0)

    def test_empty_predefined_classes(self):
        """Test with empty predefined classes."""
        checker = LabelConsistencyChecker([])
        labels = {'person': ['file1.txt']}
        issues = checker.check_labels(labels)

        # All labels should be undefined
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, IssueType.UNDEFINED)


class TestLabelIssue(unittest.TestCase):
    """Test cases for LabelIssue dataclass."""

    def test_issue_creation(self):
        """Test creating a label issue."""
        issue = LabelIssue(
            issue_type=IssueType.TYPO,
            label='persom',
            suggestion='person',
            similarity=0.92,
            count=5,
            files=['f1.txt', 'f2.txt']
        )

        self.assertEqual(issue.issue_type, IssueType.TYPO)
        self.assertEqual(issue.label, 'persom')
        self.assertEqual(issue.suggestion, 'person')
        self.assertAlmostEqual(issue.similarity, 0.92, places=2)
        self.assertEqual(issue.count, 5)

    def test_issue_equality(self):
        """Test issue equality for deduplication."""
        issue1 = LabelIssue(IssueType.TYPO, 'persom')
        issue2 = LabelIssue(IssueType.TYPO, 'persom')
        issue3 = LabelIssue(IssueType.CASE_MISMATCH, 'persom')

        self.assertEqual(issue1, issue2)
        self.assertNotEqual(issue1, issue3)

    def test_issue_hash(self):
        """Test issue hashing for set operations."""
        issue1 = LabelIssue(IssueType.TYPO, 'persom')
        issue2 = LabelIssue(IssueType.TYPO, 'persom')

        issue_set = {issue1, issue2}
        self.assertEqual(len(issue_set), 1)


class TestScanAnnotations(unittest.TestCase):
    """Test cases for annotation scanning."""

    def setUp(self):
        """Create temp directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scan_yolo_annotations(self):
        """Test scanning YOLO format annotations."""
        # Create test files
        img_path = os.path.join(self.temp_dir, 'test.jpg')
        txt_path = os.path.join(self.temp_dir, 'test.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        open(img_path, 'w').close()
        with open(txt_path, 'w') as f:
            f.write("0 0.5 0.5 0.2 0.2\n")
            f.write("1 0.3 0.3 0.1 0.1\n")
        with open(classes_path, 'w') as f:
            f.write("person\ncar\n")

        labels = LabelConsistencyChecker.scan_annotations(self.temp_dir)

        self.assertIn('person', labels)
        self.assertIn('car', labels)
        self.assertEqual(len(labels['person']), 1)

    def test_scan_voc_annotations(self):
        """Test scanning PASCAL VOC format annotations."""
        img_path = os.path.join(self.temp_dir, 'test.jpg')
        xml_path = os.path.join(self.temp_dir, 'test.xml')

        open(img_path, 'w').close()
        xml_content = """<?xml version="1.0"?>
<annotation>
    <filename>test.jpg</filename>
    <size>
        <width>100</width>
        <height>100</height>
        <depth>3</depth>
    </size>
    <object>
        <name>dog</name>
        <bndbox>
            <xmin>10</xmin>
            <ymin>10</ymin>
            <xmax>50</xmax>
            <ymax>50</ymax>
        </bndbox>
    </object>
</annotation>"""
        with open(xml_path, 'w') as f:
            f.write(xml_content)

        labels = LabelConsistencyChecker.scan_annotations(self.temp_dir)

        self.assertIn('dog', labels)

    def test_scan_empty_directory(self):
        """Test scanning empty directory."""
        labels = LabelConsistencyChecker.scan_annotations(self.temp_dir)
        self.assertEqual(len(labels), 0)

    def test_scan_with_save_dir(self):
        """Test scanning with separate save directory."""
        img_dir = os.path.join(self.temp_dir, 'images')
        save_dir = os.path.join(self.temp_dir, 'labels')
        os.makedirs(img_dir)
        os.makedirs(save_dir)

        # Image in img_dir, annotation in save_dir
        img_path = os.path.join(img_dir, 'test.jpg')
        txt_path = os.path.join(save_dir, 'test.txt')
        classes_path = os.path.join(save_dir, 'classes.txt')

        open(img_path, 'w').close()
        with open(txt_path, 'w') as f:
            f.write("0 0.5 0.5 0.2 0.2\n")
        with open(classes_path, 'w') as f:
            f.write("cat\n")

        labels = LabelConsistencyChecker.scan_annotations(img_dir, save_dir)

        self.assertIn('cat', labels)


if __name__ == '__main__':
    unittest.main()
