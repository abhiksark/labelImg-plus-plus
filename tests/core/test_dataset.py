import os

from libs.core.dataset import AnnotationResolver, DatasetSnapshot
from libs.formats.annotation_paths import (
    annotation_output_stem,
    annotation_stem_candidates,
    find_existing_annotation,
)


def _touch(path, data=b''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as output:
        output.write(data)
    return path


def test_indexed_resolver_matches_legacy_collision_contract(tmp_path):
    save_dir = tmp_path / 'labels'
    save_dir.mkdir()
    first = _touch(str(tmp_path / 'a' / 'frame.jpg'))
    second = _touch(str(tmp_path / 'b' / 'FRAME.png'))
    unique = _touch(str(tmp_path / 'b' / 'unique.png'))
    images = [first, second, unique]
    resolver = AnnotationResolver(images, str(save_dir))

    for image_path in images:
        assert list(resolver.annotation_stem_candidates(image_path)) == \
            annotation_stem_candidates(image_path, images)
        assert resolver.output_stem(image_path) == annotation_output_stem(
            image_path, str(save_dir), images)


def test_indexed_resolver_finds_specific_sidecar_without_probing(tmp_path):
    save_dir = tmp_path / 'labels'
    save_dir.mkdir()
    first = _touch(str(tmp_path / 'a' / 'frame.jpg'))
    second = _touch(str(tmp_path / 'b' / 'frame.jpg'))
    images = [first, second]
    specific = annotation_output_stem(first, str(save_dir), images)
    annotation = _touch(str(save_dir / (specific + '.xml')), b'<annotation/>')
    resolver = AnnotationResolver(images, str(save_dir))

    resolver.contains = lambda _path: (_ for _ in ()).throw(
        AssertionError('indexed lookup must not probe candidate paths'))
    assert resolver.find_existing(first) == annotation
    assert find_existing_annotation(
        first, str(save_dir), images, resolver=resolver) == annotation


def test_resolver_build_computes_raw_stems_once_per_identity(
        tmp_path, monkeypatch):
    import libs.core.dataset as dataset_module

    images = [
        _touch(str(tmp_path / str(index) / ('image_%d.jpg' % index)))
        for index in range(2000)
    ]
    original = dataset_module._raw_specific_stems
    calls = []

    def counted(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(dataset_module, '_raw_specific_stems', counted)
    resolver = AnnotationResolver(images, str(tmp_path / 'labels'))

    assert len(calls) == len(images)
    for path in images:
        assert resolver.annotation_stem_candidates(path)
    assert len(calls) == len(images)


def test_snapshot_is_immutable_and_removal_updates_mapping(tmp_path):
    first = _touch(str(tmp_path / 'a.jpg'))
    second = _touch(str(tmp_path / 'b.jpg'))
    snapshot = DatasetSnapshot.from_images(
        [first, second], root_dir=str(tmp_path), save_dir=str(tmp_path))

    assert snapshot.image_paths == (first, second)
    assert snapshot.path_to_index[second] == 1
    smaller = snapshot.without(first)
    assert snapshot.image_paths == (first, second)
    assert smaller.image_paths == (second,)
    assert smaller.path_to_index[second] == 0


def test_snapshot_scan_reports_progress_and_honors_extensions(tmp_path):
    _touch(str(tmp_path / 'nested' / 'b.png'))
    _touch(str(tmp_path / 'a.jpg'))
    _touch(str(tmp_path / 'ignored.txt'))
    progress = []

    snapshot = DatasetSnapshot.scan(
        str(tmp_path), save_dir=str(tmp_path), generation=7,
        extensions=('.jpg', '.png'), progress=lambda *value: progress.append(value))

    assert snapshot.generation == 7
    assert [os.path.basename(path) for path in snapshot.image_paths] == [
        'a.jpg', 'b.png']
    assert progress[-1] == (3, 2)


def test_incremental_annotation_update_refreshes_indexed_lookup(tmp_path):
    image = _touch(str(tmp_path / 'image.jpg'))
    snapshot = DatasetSnapshot.from_images(
        [image], root_dir=str(tmp_path), save_dir=str(tmp_path))
    annotation = str(tmp_path / 'image.xml')
    assert snapshot.resolver.find_existing(image) is None

    _touch(annotation, b'<annotation/>')
    updated = snapshot.with_annotation_file(
        annotation, image_path=image)

    assert updated.resolver.find_existing(image) == annotation
