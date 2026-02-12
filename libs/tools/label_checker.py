# libs/tools/label_checker.py
"""Label consistency checker for detecting typos and inconsistencies."""

import os
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import IntEnum
from typing import Dict, List, Optional, Set, Tuple

from libs.formats.yolo_io import YoloReader
from libs.formats.pascal_voc_io import PascalVocReader
from libs.formats.create_ml_io import CreateMLReader


class IssueType(IntEnum):
    """Types of label consistency issues."""
    TYPO = 1           # Similar to predefined class (likely typo)
    CASE_MISMATCH = 2  # Same letters, different case
    WHITESPACE = 3     # Has leading/trailing whitespace
    UNDEFINED = 4      # Not in predefined classes (no similar match)
    DUPLICATE = 5      # Same label appears with different variations


@dataclass
class LabelIssue:
    """Represents a label consistency issue."""
    issue_type: IssueType
    label: str
    suggestion: Optional[str] = None
    similarity: float = 0.0
    count: int = 0
    files: List[str] = field(default_factory=list)

    def __hash__(self):
        return hash((self.issue_type, self.label))

    def __eq__(self, other):
        if not isinstance(other, LabelIssue):
            return False
        return self.issue_type == other.issue_type and self.label == other.label


class LabelConsistencyChecker:
    """Check label consistency across a dataset.

    Detects:
    - Typos (fuzzy matching against predefined classes)
    - Case mismatches ("Dog" vs "dog")
    - Whitespace issues ("dog " vs "dog")
    - Undefined labels (not in predefined classes)
    """

    def __init__(
        self,
        predefined_classes: List[str],
        similarity_threshold: float = 0.8
    ):
        """Initialize the checker.

        Args:
            predefined_classes: List of valid/expected class names
            similarity_threshold: Minimum similarity ratio for typo detection (0-1)
        """
        self.predefined_classes = list(predefined_classes)
        self.predefined_set = set(predefined_classes)
        self.predefined_lower = {c.lower(): c for c in predefined_classes}
        self.similarity_threshold = similarity_threshold

    def check_labels(
        self,
        labels_with_files: Dict[str, List[str]]
    ) -> List[LabelIssue]:
        """Check a collection of labels for consistency issues.

        Args:
            labels_with_files: Dict mapping label -> list of file paths

        Returns:
            List of LabelIssue objects describing found issues
        """
        issues = []
        seen_issues = set()

        for label, files in labels_with_files.items():
            label_issues = self._check_single_label(label)
            for issue in label_issues:
                issue.count = len(files)
                issue.files = files
                issue_key = (issue.issue_type, issue.label)
                if issue_key not in seen_issues:
                    issues.append(issue)
                    seen_issues.add(issue_key)

        # Sort by issue type, then by count (descending)
        issues.sort(key=lambda x: (x.issue_type, -x.count))
        return issues

    def _check_single_label(self, label: str) -> List[LabelIssue]:
        """Check a single label for issues.

        Args:
            label: The label to check

        Returns:
            List of issues found for this label
        """
        issues = []
        stripped = label.strip()

        # Check for whitespace issues
        if label != stripped:
            issues.append(LabelIssue(
                issue_type=IssueType.WHITESPACE,
                label=label,
                suggestion=stripped,
                similarity=1.0
            ))
            label = stripped  # Continue checking the stripped version

        # Exact match - no issues
        if label in self.predefined_set:
            return issues

        # Check for case mismatch
        label_lower = label.lower()
        if label_lower in self.predefined_lower:
            correct = self.predefined_lower[label_lower]
            if label != correct:
                issues.append(LabelIssue(
                    issue_type=IssueType.CASE_MISMATCH,
                    label=label,
                    suggestion=correct,
                    similarity=1.0
                ))
            return issues

        # Check for typos using fuzzy matching
        best_match, similarity = self._find_best_match(label)
        if similarity >= self.similarity_threshold:
            issues.append(LabelIssue(
                issue_type=IssueType.TYPO,
                label=label,
                suggestion=best_match,
                similarity=similarity
            ))
        else:
            # Undefined label (no close match)
            issues.append(LabelIssue(
                issue_type=IssueType.UNDEFINED,
                label=label,
                suggestion=best_match if similarity > 0.5 else None,
                similarity=similarity
            ))

        return issues

    def _find_best_match(self, label: str) -> Tuple[Optional[str], float]:
        """Find the best matching predefined class for a label.

        Args:
            label: The label to match

        Returns:
            Tuple of (best matching class, similarity ratio)
        """
        best_match = None
        best_ratio = 0.0

        label_lower = label.lower()
        for predefined in self.predefined_classes:
            # Use SequenceMatcher for fuzzy matching
            ratio = SequenceMatcher(
                None,
                label_lower,
                predefined.lower()
            ).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_match = predefined

        return best_match, best_ratio

    def normalize_label(self, label: str) -> str:
        """Normalize a label to its canonical form.

        Args:
            label: The label to normalize

        Returns:
            Normalized label (stripped, correct case if in predefined)
        """
        stripped = label.strip()
        lower = stripped.lower()
        if lower in self.predefined_lower:
            return self.predefined_lower[lower]
        return stripped

    @staticmethod
    def scan_annotations(
        directory: str,
        save_dir: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """Scan a directory for annotations and collect all labels.

        Args:
            directory: Directory containing images
            save_dir: Optional separate directory for annotations

        Returns:
            Dict mapping label -> list of annotation file paths
        """
        labels_with_files: Dict[str, List[str]] = defaultdict(list)
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff'}

        # Find all image files
        for root, _, files in os.walk(directory):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in image_extensions:
                    continue

                image_path = os.path.join(root, filename)
                base_name = os.path.splitext(filename)[0]

                # Determine annotation directory
                ann_dir = save_dir if save_dir else root

                # Check for YOLO format (.txt)
                txt_path = os.path.join(ann_dir, base_name + '.txt')
                if os.path.isfile(txt_path):
                    labels = LabelConsistencyChecker._extract_yolo_labels(
                        txt_path, ann_dir
                    )
                    for label in labels:
                        labels_with_files[label].append(txt_path)
                    continue

                # Check for PASCAL VOC format (.xml)
                xml_path = os.path.join(ann_dir, base_name + '.xml')
                if os.path.isfile(xml_path):
                    labels = LabelConsistencyChecker._extract_voc_labels(xml_path)
                    for label in labels:
                        labels_with_files[label].append(xml_path)
                    continue

        # Check for CreateML format (single JSON file)
        json_path = os.path.join(save_dir or directory, 'annotations.json')
        if os.path.isfile(json_path):
            labels_by_image = LabelConsistencyChecker._extract_createml_labels(
                json_path
            )
            for label, images in labels_by_image.items():
                labels_with_files[label].extend(
                    [f"{json_path}:{img}" for img in images]
                )

        return dict(labels_with_files)

    @staticmethod
    def _extract_yolo_labels(txt_path: str, ann_dir: str) -> Set[str]:
        """Extract labels from a YOLO annotation file.

        Args:
            txt_path: Path to the .txt annotation file
            ann_dir: Directory containing classes.txt

        Returns:
            Set of label names found in the file
        """
        labels = set()
        classes_path = os.path.join(ann_dir, 'classes.txt')

        if not os.path.isfile(classes_path):
            return labels

        try:
            with open(classes_path, 'r') as f:
                classes = [line.strip() for line in f if line.strip()]

            with open(txt_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        try:
                            class_idx = int(parts[0])
                            if 0 <= class_idx < len(classes):
                                labels.add(classes[class_idx])
                        except ValueError:
                            continue
        except (IOError, OSError):
            pass

        return labels

    @staticmethod
    def _extract_voc_labels(xml_path: str) -> Set[str]:
        """Extract labels from a PASCAL VOC annotation file.

        Args:
            xml_path: Path to the .xml annotation file

        Returns:
            Set of label names found in the file
        """
        labels = set()
        try:
            reader = PascalVocReader(xml_path)
            for shape in reader.get_shapes():
                if shape and len(shape) > 0:
                    labels.add(shape[0])  # First element is label
        except Exception:
            pass
        return labels

    @staticmethod
    def _extract_createml_labels(json_path: str) -> Dict[str, List[str]]:
        """Extract labels from a CreateML annotation file.

        Args:
            json_path: Path to the annotations.json file

        Returns:
            Dict mapping label -> list of image filenames
        """
        labels_by_image: Dict[str, List[str]] = defaultdict(list)
        try:
            import json
            with open(json_path, 'r') as f:
                data = json.load(f)

            if isinstance(data, list):
                for item in data:
                    image_name = item.get('image', 'unknown')
                    annotations = item.get('annotations', [])
                    for ann in annotations:
                        label = ann.get('label')
                        if label:
                            labels_by_image[label].append(image_name)
        except Exception:
            pass

        return dict(labels_by_image)
