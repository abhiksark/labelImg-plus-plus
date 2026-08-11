import json
import os

from libs.core.dataset import DatasetSnapshot
from libs.formats.annotation_probe import SharedJsonCache, probe


def test_shared_coco_document_is_loaded_once(tmp_path, monkeypatch):
    images = []
    coco_images = []
    annotations = []
    for index in range(100):
        name = 'image_%03d.jpg' % index
        path = tmp_path / name
        path.write_bytes(b'image')
        images.append(str(path))
        coco_images.append({'id': index, 'file_name': name})
        annotations.append({
            'id': index,
            'image_id': index,
            'category_id': 1,
            'bbox': [0, 0, 1, 1],
        })
    annotation_path = tmp_path / 'annotations.json'
    annotation_path.write_text(json.dumps({
        'images': coco_images,
        'annotations': annotations,
        'categories': [{'id': 1, 'name': 'object'}],
    }))
    snapshot = DatasetSnapshot.from_images(
        images, root_dir=str(tmp_path), save_dir=str(tmp_path))
    cache = SharedJsonCache()
    loads = []
    original = json.load

    def counted(stream, *args, **kwargs):
        loads.append(os.fspath(stream.name))
        return original(stream, *args, **kwargs)

    monkeypatch.setattr(json, 'load', counted)
    results = [
        probe(path, str(tmp_path), resolver=snapshot.resolver,
              json_cache=cache)
        for path in images
    ]

    assert len(loads) == 1
    assert all(result.fmt == 'coco' for result in results)
    assert all(result.labels == ['object'] for result in results)


def test_shared_json_cache_reloads_after_fingerprint_change(tmp_path):
    path = tmp_path / 'annotations.json'
    path.write_text('[]')
    cache = SharedJsonCache()
    assert cache.get(str(path)) == []

    path.write_text('[{"image": "a.jpg", "annotations": []}]')
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1))
    assert cache.get(str(path))[0]['image'] == 'a.jpg'


def test_shared_coco_annotations_are_indexed_once(tmp_path, monkeypatch):
    class CountingList(list):
        iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    images = []
    coco_images = []
    annotations = CountingList()
    for index in range(100):
        name = 'image_%03d.jpg' % index
        image_path = tmp_path / name
        image_path.write_bytes(b'image')
        images.append(str(image_path))
        coco_images.append({'id': index, 'file_name': name})
        annotations.append({'image_id': index, 'category_id': 1})
    annotation_path = tmp_path / 'annotations.json'
    annotation_path.write_text('{}')
    data = {
        'images': coco_images,
        'annotations': annotations,
        'categories': [{'id': 1, 'name': 'object'}],
    }
    monkeypatch.setattr(json, 'load', lambda _stream: data)
    snapshot = DatasetSnapshot.from_images(
        images, root_dir=str(tmp_path), save_dir=str(tmp_path))
    cache = SharedJsonCache()

    for image_path in images:
        assert probe(
            image_path, str(tmp_path), resolver=snapshot.resolver,
            json_cache=cache).labels == ['object']

    assert annotations.iterations == 1
