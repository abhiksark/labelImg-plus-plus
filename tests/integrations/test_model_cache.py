import hashlib
import socket
import urllib.error

import pytest

from libs.integrations import model_cache
from libs.integrations.model_manifest import ModelArtifact, ModelManifest


class ChunkedResponse:
    headers = {'Content-Length': '8'}

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        self.read_count += 1
        return self.chunks.pop(0) if self.chunks else b''


class Response(ChunkedResponse):
    def __init__(self, payload):
        super().__init__([payload])
        self.headers = {'Content-Length': str(len(payload))}


@pytest.fixture
def fake_manifest():
    payload = b'aaaabbbb'
    return ModelManifest(
        'fake', 'Fake model', 'Test segmentation', 'Test provider',
        (ModelArtifact(
            'fake.onnx', 'https://provider.invalid/fake.onnx',
            len(payload), hashlib.sha256(payload).hexdigest()),))


def test_cancel_removes_part_and_never_retries(tmp_path, fake_manifest,
                                                monkeypatch):
    """Catches a downloader that retries cancellation or leaves partial files."""
    calls = []
    response = ChunkedResponse([b'a' * 4, b'b' * 4])
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request, timeout=None:
                        calls.append(request) or response)
    cancelled = lambda: response.read_count >= 1
    with pytest.raises(model_cache.ModelDownloadCancelled):
        model_cache.download_manifest(
            fake_manifest, str(tmp_path), cancelled=cancelled)
    assert len(calls) == 1
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_wrong_content_length_is_validation_failure(tmp_path, fake_manifest,
                                                    monkeypatch):
    """Catches trusting a provider response whose declared size is wrong."""
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request, timeout=None: Response(b'short'))
    with pytest.raises(model_cache.ModelValidationError, match='size'):
        model_cache.download_manifest(fake_manifest, str(tmp_path))
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_truncated_body_is_validation_failure(tmp_path, fake_manifest,
                                              monkeypatch):
    """Catches promoting a short body when the provider header is correct."""
    response = Response(b'short')
    response.headers = {'Content-Length': '8'}
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request, timeout=None: response)
    with pytest.raises(model_cache.ModelValidationError, match='size'):
        model_cache.download_manifest(fake_manifest, str(tmp_path))
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_network_failure_is_offline_error(tmp_path, fake_manifest, monkeypatch):
    """Catches classifying a connectivity failure as a provider failure."""
    monkeypatch.setattr(
        model_cache.urllib.request, 'urlopen',
        lambda request, timeout=None:
        (_ for _ in ()).throw(urllib.error.URLError('offline')))
    with pytest.raises(model_cache.ModelOfflineError, match='offline'):
        model_cache.download_manifest(fake_manifest, str(tmp_path))


def test_http_failure_is_provider_error(tmp_path, fake_manifest, monkeypatch):
    """Catches HTTPError falling through its URLError base class as offline."""
    error = urllib.error.HTTPError(
        fake_manifest.artifacts[0].url, 503, 'unavailable', {}, None)
    monkeypatch.setattr(
        model_cache.urllib.request, 'urlopen',
        lambda request, timeout=None: (_ for _ in ()).throw(error))
    with pytest.raises(model_cache.ModelProviderError, match='503'):
        model_cache.download_manifest(fake_manifest, str(tmp_path))


def test_checksum_mismatch_is_validation_failure(tmp_path, fake_manifest,
                                                 monkeypatch):
    """Catches promoting bytes that do not match the pinned manifest digest."""
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request, timeout=None: Response(b'ccccdddd'))
    with pytest.raises(model_cache.ModelValidationError, match='checksum'):
        model_cache.download_manifest(fake_manifest, str(tmp_path))
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_invalid_download_never_fsyncs_temporary_file(tmp_path, fake_manifest,
                                                      monkeypatch):
    """Catches making invalid bytes durable before their checksum is checked."""
    fsync_calls = []
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request, timeout=None: Response(b'ccccdddd'))
    monkeypatch.setattr(model_cache.os, 'fsync',
                        lambda descriptor: fsync_calls.append(descriptor))
    with pytest.raises(model_cache.ModelValidationError, match='checksum'):
        model_cache.download_manifest(fake_manifest, str(tmp_path))
    assert fsync_calls == []
    assert not list(tmp_path.glob('*.part'))


def test_connect_timeout_after_cancel_cleans_without_retry(
        tmp_path, fake_manifest, monkeypatch):
    """Catches an unbounded cancelled connect that never reaches cleanup."""
    calls = []
    state = {'cancelled': False}

    def stalled_connect(request, timeout=None):
        calls.append((request, timeout))
        state['cancelled'] = True
        raise socket.timeout('connect stalled')

    monkeypatch.setattr(model_cache.urllib.request, 'urlopen', stalled_connect)
    with pytest.raises(model_cache.ModelDownloadCancelled):
        model_cache.download_manifest(
            fake_manifest, str(tmp_path),
            cancelled=lambda: state['cancelled'], timeout=.01)
    assert calls == [(fake_manifest.artifacts[0].url, .01)]
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_read_timeout_after_cancel_removes_active_part(
        tmp_path, fake_manifest, monkeypatch):
    """Catches a stalled body read retaining a partial artifact after Cancel."""
    calls = []
    state = {'cancelled': False}

    class StalledResponse(ChunkedResponse):
        headers = {'Content-Length': '8'}

        def __init__(self):
            super().__init__([])

        def read(self, _size):
            self.read_count += 1
            state['cancelled'] = True
            raise socket.timeout('read stalled')

    monkeypatch.setattr(
        model_cache.urllib.request, 'urlopen',
        lambda request, timeout=None:
        calls.append((request, timeout)) or StalledResponse())
    with pytest.raises(model_cache.ModelDownloadCancelled):
        model_cache.download_manifest(
            fake_manifest, str(tmp_path),
            cancelled=lambda: state['cancelled'], timeout=.01)
    assert calls == [(fake_manifest.artifacts[0].url, .01)]
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_uncancelled_timeout_is_offline_without_promotion(
        tmp_path, fake_manifest, monkeypatch):
    """Catches presenting a timed-out provider as cancellation or success."""
    calls = []

    def timed_out(request, timeout=None):
        calls.append((request, timeout))
        raise socket.timeout('connect stalled')

    monkeypatch.setattr(model_cache.urllib.request, 'urlopen', timed_out)
    with pytest.raises(model_cache.ModelOfflineError, match='stalled'):
        model_cache.download_manifest(fake_manifest, str(tmp_path), timeout=.01)
    assert calls == [(fake_manifest.artifacts[0].url, .01)]
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_builtin_timeout_after_cancel_is_cancelled(
        tmp_path, fake_manifest, monkeypatch):
    """Catches Python's non-socket timeout class bypassing cancellation."""
    state = {'cancelled': False}

    def timed_out(_request, timeout=None):
        state['cancelled'] = True
        raise TimeoutError('connect stalled')

    monkeypatch.setattr(model_cache.urllib.request, 'urlopen', timed_out)
    with pytest.raises(model_cache.ModelDownloadCancelled):
        model_cache.download_manifest(
            fake_manifest, str(tmp_path),
            cancelled=lambda: state['cancelled'], timeout=.01)
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_download_promotes_verified_file_and_reports_progress(
        tmp_path, fake_manifest, monkeypatch):
    """Catches non-atomic promotion or reporting bytes unrelated to written data."""
    progress = []
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request, timeout=None:
                        ChunkedResponse([b'aaaa', b'bbbb']))
    paths = model_cache.download_manifest(
        fake_manifest, str(tmp_path), progress=progress.append)
    assert paths == (str(tmp_path / 'fake.onnx'),)
    assert (tmp_path / 'fake.onnx').read_bytes() == b'aaaabbbb'
    assert not list(tmp_path.glob('*.part'))
    assert progress[-1] == model_cache.ModelDownloadProgress(
        'fake.onnx', 8, 8, 8, 8)


def test_cached_model_paths_requires_every_valid_artifact(tmp_path, fake_manifest):
    """Catches treating a missing or tampered manifest pair as cache-ready."""
    artifact = fake_manifest.artifacts[0]
    path = tmp_path / artifact.name
    path.write_bytes(b'aaaabbbb')
    assert model_cache.cached_model_paths(fake_manifest, str(tmp_path)) == (
        str(path),)
    path.write_bytes(b'changed!')
    assert model_cache.cached_model_paths(fake_manifest, str(tmp_path)) is None


def test_cached_model_paths_never_accepts_partial_artifacts(tmp_path,
                                                            fake_manifest):
    """Catches considering an interrupted .part file usable by a backend."""
    (tmp_path / 'fake.onnx.part').write_bytes(b'aaaabbbb')
    assert model_cache.cached_model_paths(fake_manifest, str(tmp_path)) is None


def test_cached_model_paths_rejects_incomplete_manifest_pair(tmp_path):
    """Catches treating one valid default artifact as a usable model pair."""
    encoder = ModelArtifact(
        'encoder.onnx', 'https://provider.invalid/encoder.onnx', 3,
        hashlib.sha256(b'enc').hexdigest())
    decoder = ModelArtifact(
        'decoder.onnx', 'https://provider.invalid/decoder.onnx', 3,
        hashlib.sha256(b'dec').hexdigest())
    manifest = ModelManifest(
        'pair', 'Pair', 'Test segmentation', 'Test provider',
        (encoder, decoder))
    (tmp_path / encoder.name).write_bytes(b'enc')
    assert model_cache.cached_model_paths(manifest, str(tmp_path)) is None
    (tmp_path / decoder.name).write_bytes(b'dec')
    assert model_cache.cached_model_paths(manifest, str(tmp_path)) == (
        str(tmp_path / encoder.name), str(tmp_path / decoder.name))


def test_default_model_paths_remain_stable(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path))
    paths = model_cache.default_model_paths()
    assert len(paths) == 2
    assert paths[0].endswith('mobile_sam.encoder.onnx')
    assert paths[1].endswith('mobile_sam.decoder.onnx')
