from PyQt5.QtGui import QImage

from libs.core.save_pipeline import SaveRequest, write_save_request
from libs.formats.labelFile import LabelFileFormat


def _image(path):
    image = QImage(20, 10, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(path)


def _request(image_path, annotation_path):
    return SaveRequest(
        image_path=str(image_path),
        annotation_path=str(annotation_path),
        label_file_format=LabelFileFormat.PASCAL_VOC,
        shapes=(), class_list=(), verified=False, revision=1)


def test_cancelled_save_leaves_existing_target_unchanged(tmp_path):
    image_path = tmp_path / 'image.png'
    annotation_path = tmp_path / 'image.xml'
    _image(str(image_path))
    annotation_path.write_text('original')

    result = write_save_request(
        _request(image_path, annotation_path), cancelled=lambda: True)

    assert result is None
    assert annotation_path.read_text() == 'original'


def test_save_enters_non_cancellable_phase_before_atomic_replace(
        tmp_path, monkeypatch):
    image_path = tmp_path / 'image.png'
    annotation_path = tmp_path / 'image.xml'
    _image(str(image_path))
    committing = []
    import libs.core.save_pipeline as pipeline
    original_replace = pipeline.os.replace

    def checked_replace(source, target):
        assert committing == [True]
        return original_replace(source, target)

    monkeypatch.setattr(pipeline.os, 'replace', checked_replace)

    result = write_save_request(
        _request(image_path, annotation_path),
        begin_commit=lambda: committing.append(True))

    assert result == str(annotation_path)
    assert '<annotation' in annotation_path.read_text()
