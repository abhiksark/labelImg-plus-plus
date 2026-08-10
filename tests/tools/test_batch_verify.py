import xml.etree.ElementTree as ET
import json

import pytest

from libs.core.dataset import DatasetSnapshot
from libs.core.task_coordinator import JobCancelled
from libs.tools.batch_verify import batch_verify_atomic


class Handle:
    def __init__(self, cancel_after=None):
        self.cancel_after = cancel_after
        self.checks = 0
        self.progress = []
        self.committing = False

    def check_cancelled(self):
        self.checks += 1
        if self.cancel_after is not None and self.checks >= self.cancel_after:
            raise JobCancelled()

    def report_progress(self, value):
        self.progress.append(value)

    def begin_non_cancellable(self):
        self.check_cancelled()
        self.committing = True


def _dataset(tmp_path, count=3):
    images = []
    for index in range(count):
        image = tmp_path / ('image-%d.jpg' % index)
        image.write_bytes(b'image')
        annotation = tmp_path / ('image-%d.xml' % index)
        annotation.write_text('<annotation><object/></annotation>')
        images.append(str(image))
    return images, DatasetSnapshot.from_images(
        images, root_dir=str(tmp_path), save_dir=str(tmp_path))


def test_batch_verify_cancellation_before_commit_leaves_every_file(tmp_path):
    images, snapshot = _dataset(tmp_path)
    handle = Handle(cancel_after=3)

    with pytest.raises(JobCancelled):
        batch_verify_atomic(
            images, str(tmp_path), True, handle,
            resolver=snapshot.resolver)

    for index in range(len(images)):
        root = ET.parse(tmp_path / ('image-%d.xml' % index)).getroot()
        assert 'verified' not in root.attrib


def test_batch_verify_commits_prepared_files_and_reports_progress(tmp_path):
    images, snapshot = _dataset(tmp_path)
    handle = Handle()

    committed, failures = batch_verify_atomic(
        images, str(tmp_path), True, handle,
        resolver=snapshot.resolver)

    assert committed == len(images)
    assert failures == []
    assert handle.committing
    assert handle.progress[-1] == (len(images), len(images))
    for index in range(len(images)):
        root = ET.parse(tmp_path / ('image-%d.xml' % index)).getroot()
        assert root.attrib['verified'] == 'yes'


def test_batch_verify_reports_shared_json_as_unsupported(tmp_path):
    images = []
    coco_images = []
    for index in range(2):
        image = tmp_path / ('image-%d.jpg' % index)
        image.write_bytes(b'image')
        images.append(str(image))
        coco_images.append({
            'id': index + 1, 'file_name': image.name,
        })
    (tmp_path / 'annotations.json').write_text(json.dumps({
        'images': coco_images, 'annotations': [], 'categories': [],
    }))
    snapshot = DatasetSnapshot.from_images(
        images, root_dir=str(tmp_path), save_dir=str(tmp_path))

    committed, failures = batch_verify_atomic(
        images, str(tmp_path), True, Handle(),
        resolver=snapshot.resolver)

    assert committed == 0
    assert [path for path, _reason in failures] == images
    assert all('not a PASCAL VOC' in reason for _path, reason in failures)
