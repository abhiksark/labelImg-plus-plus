import time

from PyQt5.QtWidgets import QApplication

from libs.core.annotation_catalog import AnnotationCatalog, HAS_LABELS
from libs.core.dataset import DatasetSnapshot
from libs.core.task_coordinator import TaskCoordinator


_APP = QApplication.instance() or QApplication([])


def _wait(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _APP.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def test_catalog_fans_status_and_statistics_from_one_index(tmp_path):
    images = []
    for index in range(20):
        image = tmp_path / ('image-%02d.jpg' % index)
        image.write_bytes(b'image')
        images.append(str(image))
        if index % 2:
            (tmp_path / ('image-%02d.xml' % index)).write_text(
                '<annotation><filename>x.jpg</filename><size><width>1</width>'
                '<height>1</height><depth>3</depth></size><object>'
                '<name>cat</name><difficult>0</difficult><bndbox><xmin>0</xmin>'
                '<ymin>0</ymin><xmax>1</xmax><ymax>1</ymax></bndbox>'
                '</object></annotation>')
    snapshot = DatasetSnapshot.from_images(
        images, root_dir=str(tmp_path), save_dir=str(tmp_path), generation=1)
    coordinator = TaskCoordinator(logical_cpus=2)
    catalog = AnnotationCatalog(coordinator, batch_size=4)
    batches = []
    statistics = []
    catalog.batch_ready.connect(batches.append)
    catalog.statistics_ready.connect(
        lambda *value: statistics.append(value))

    catalog.start(snapshot)
    catalog.request_statistics()

    assert _wait(lambda: bool(statistics))
    assert len(catalog.entries) == 20
    assert sum(entry.status == HAS_LABELS
               for entry in catalog.entries.values()) == 10
    assert statistics[-1][:3] == (20, 10, 0)
    assert statistics[-1][3] == {'cat': 10}
    assert batches
    coordinator.shutdown()
