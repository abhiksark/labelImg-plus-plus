# libs/statsWidget.py
"""Statistics widget for displaying annotation statistics."""

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QGroupBox, QLabel, QProgressBar,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QPushButton, QStyle
    )
except ImportError:
    from PyQt4.QtGui import (
        QWidget, QVBoxLayout, QGroupBox, QLabel, QProgressBar,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QPushButton, QStyle
    )
    from PyQt4.QtCore import Qt


class StatsWidget(QWidget):
    """Widget displaying annotation statistics for the dataset."""

    def __init__(self, parent=None):
        super(StatsWidget, self).__init__(parent)
        self._setup_ui()
        self._label_counts = {}
        self._dataset_stats = {
            'total': 0,
            'annotated': 0,
            'verified': 0
        }
        self._current_image_stats = {
            'annotations': 0,
            'labels': []
        }

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Dataset Statistics Section
        dataset_group = QGroupBox("Dataset Statistics")
        dataset_layout = QVBoxLayout(dataset_group)
        dataset_layout.setSpacing(4)

        self.total_images_label = QLabel("Images: 0")
        self.annotated_label = QLabel("Annotated: 0 (0%)")
        self.verified_label = QLabel("Verified: 0 (0%)")

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Annotation Progress: %p%")

        dataset_layout.addWidget(self.total_images_label)
        dataset_layout.addWidget(self.annotated_label)
        dataset_layout.addWidget(self.verified_label)
        dataset_layout.addWidget(self.progress_bar)

        layout.addWidget(dataset_group)

        # Label Distribution Section
        label_group = QGroupBox("Label Distribution")
        label_layout = QVBoxLayout(label_group)

        self.label_table = QTableWidget()
        self.label_table.setColumnCount(2)
        self.label_table.setHorizontalHeaderLabels(["Label", "Count"])
        self.label_table.horizontalHeader().setStretchLastSection(True)
        self.label_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.label_table.verticalHeader().setVisible(False)
        self.label_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.label_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.label_table.setMaximumHeight(200)

        label_layout.addWidget(self.label_table)

        layout.addWidget(label_group)

        # Current Image Section
        current_group = QGroupBox("Current Image")
        current_layout = QVBoxLayout(current_group)
        current_layout.setSpacing(4)

        self.current_annotations_label = QLabel("Annotations: 0")
        self.current_labels_label = QLabel("Labels: -")
        self.current_labels_label.setWordWrap(True)

        current_layout.addWidget(self.current_annotations_label)
        current_layout.addWidget(self.current_labels_label)

        layout.addWidget(current_group)

        # Refresh Button
        self.refresh_btn = QPushButton("Refresh Statistics")
        self.refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        layout.addWidget(self.refresh_btn)

        # Spacer
        layout.addStretch()

        self.setLayout(layout)

    def update_dataset_stats(self, total, annotated, verified):
        """Update dataset-level statistics.

        Args:
            total: Total number of images
            annotated: Number of images with annotations
            verified: Number of verified images
        """
        self._dataset_stats = {
            'total': total,
            'annotated': annotated,
            'verified': verified
        }

        self.total_images_label.setText(f"Images: {total}")

        if total > 0:
            annotated_pct = (annotated / total) * 100
            verified_pct = (verified / total) * 100
            self.annotated_label.setText(f"Annotated: {annotated} ({annotated_pct:.0f}%)")
            self.verified_label.setText(f"Verified: {verified} ({verified_pct:.0f}%)")
            self.progress_bar.setValue(int(annotated_pct))
        else:
            self.annotated_label.setText("Annotated: 0 (0%)")
            self.verified_label.setText("Verified: 0 (0%)")
            self.progress_bar.setValue(0)

    def update_label_distribution(self, label_counts):
        """Update label distribution table.

        Args:
            label_counts: Dict mapping label names to counts
        """
        self._label_counts = label_counts

        # Sort by count descending
        sorted_labels = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)

        self.label_table.setRowCount(len(sorted_labels))

        for row, (label, count) in enumerate(sorted_labels):
            label_item = QTableWidgetItem(label)
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.label_table.setItem(row, 0, label_item)
            self.label_table.setItem(row, 1, count_item)

    def update_current_image_stats(self, annotations_count, labels):
        """Update current image statistics.

        Args:
            annotations_count: Number of annotations in current image
            labels: List of label names used in current image
        """
        self._current_image_stats = {
            'annotations': annotations_count,
            'labels': labels
        }

        self.current_annotations_label.setText(f"Annotations: {annotations_count}")

        if labels:
            unique_labels = sorted(set(labels))
            self.current_labels_label.setText(f"Labels: {', '.join(unique_labels)}")
        else:
            self.current_labels_label.setText("Labels: -")

    def clear_stats(self):
        """Clear all statistics."""
        self.update_dataset_stats(0, 0, 0)
        self.update_label_distribution({})
        self.update_current_image_stats(0, [])

    def get_dataset_stats(self):
        """Return current dataset statistics."""
        return self._dataset_stats.copy()

    def get_label_counts(self):
        """Return current label counts."""
        return self._label_counts.copy()

    def get_current_image_stats(self):
        """Return current image statistics."""
        return self._current_image_stats.copy()
