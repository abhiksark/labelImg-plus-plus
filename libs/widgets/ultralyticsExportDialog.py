"""Configuration dialog for Ultralytics detection dataset export."""

from PyQt6.QtWidgets import QLabel

from libs.widgets.splitDialog import SplitDialog


class UltralyticsExportDialog(SplitDialog):
    """Reuse deterministic split controls with export-specific guidance."""

    def __init__(self, parent=None, image_count=0, default_dir=''):
        super().__init__(parent, image_count, default_dir)
        self.setWindowTitle('Export Ultralytics Dataset')
        self.run_btn.setText('Export')
        self.stratified_cb.setChecked(False)
        self.stratified_cb.hide()
        self._output_dir = default_dir + '_ultralytics' if default_dir else ''
        self.dir_label.setText(self._output_dir or '(select)')

        note = QLabel(
            'Creates images/train, images/val, images/test and matching '
            'labels directories with a data.yaml class map. Polygon '
            'annotations are exported as detection bounding boxes.')
        note.setWordWrap(True)
        self.layout().insertWidget(1, note)
