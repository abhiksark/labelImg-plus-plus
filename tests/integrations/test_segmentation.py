import hashlib

import pytest

from libs.integrations import model_cache, segmentation
from libs.integrations.model_manifest import ModelArtifact, ModelManifest
from libs.integrations.segmentation import SegmentationBackend, sam_available
from libs.utils.constants import SETTING_SAM_DECODER, SETTING_SAM_ENCODER


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        SegmentationBackend()


def test_sam_available_returns_bool():
    assert isinstance(sam_available(), bool)


def test_sam_available_false_when_a_dep_missing(monkeypatch):
    import importlib.util as iu
    real = iu.find_spec

    def fake(name, *a, **k):
        return None if name == "onnxruntime" else real(name, *a, **k)

    monkeypatch.setattr(iu, "find_spec", fake)
    assert sam_available() is False


def test_sam_available_does_not_require_torch(monkeypatch):
    import importlib.util as iu
    real = iu.find_spec
    probed = []

    def fake(name, *a, **k):
        probed.append(name)
        return real(name, *a, **k)

    monkeypatch.setattr(iu, "find_spec", fake)
    sam_available()
    assert "torch" not in probed and "mobile_sam" not in probed


def test_predict_before_set_image_raises_clear_error():
    pytest.importorskip("onnxruntime")
    from libs.integrations.segmentation import OnnxSamBackend
    backend = OnnxSamBackend.__new__(OnnxSamBackend)   # skip session loading
    backend._embeddings = None
    with pytest.raises(RuntimeError, match="set_image"):
        backend.predict([(1, 2)], [1])


def test_set_image_clamps_degenerate_aspect_ratio(monkeypatch):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    pytest.importorskip("onnxruntime")
    from libs.integrations.segmentation import OnnxSamBackend

    class _FakeEncoder:
        def run(self, names, feeds):
            arr = feeds["input_image"]
            assert arr.shape[0] >= 1 and arr.shape[1] >= 1
            return [np.zeros((1, 256, 64, 64), dtype=np.float32)]

    backend = OnnxSamBackend.__new__(OnnxSamBackend)
    backend._encoder = _FakeEncoder()
    rgb = np.zeros((1, 4000, 3), dtype=np.uint8)       # 4000:1 aspect ratio
    backend.set_image(rgb)                             # must not raise
    assert backend.image_is_set


def test_load_backend_uses_complete_custom_paths(tmp_path, monkeypatch):
    """Catches rejecting a complete user-supplied encoder/decoder pair."""
    encoder = tmp_path / 'custom.encoder.onnx'
    decoder = tmp_path / 'custom.decoder.onnx'
    encoder.write_bytes(b'encoder')
    decoder.write_bytes(b'decoder')
    loaded = []

    class FakeBackend:
        def __init__(self, encoder_path, decoder_path):
            loaded.append((encoder_path, decoder_path))

    monkeypatch.setattr(segmentation, 'OnnxSamBackend', FakeBackend)
    backend, error = segmentation.load_backend({
        SETTING_SAM_ENCODER: str(encoder),
        SETTING_SAM_DECODER: str(decoder),
    })
    assert isinstance(backend, FakeBackend)
    assert error is None
    assert loaded == [(str(encoder), str(decoder))]


@pytest.fixture
def small_manifest():
    encoder = ModelArtifact(
        'small.encoder.onnx', 'https://provider.invalid/small.encoder.onnx', 3,
        hashlib.sha256(b'enc').hexdigest())
    decoder = ModelArtifact(
        'small.decoder.onnx', 'https://provider.invalid/small.decoder.onnx', 3,
        hashlib.sha256(b'dec').hexdigest())
    return ModelManifest(
        'small', 'Small', 'Test segmentation', 'Test provider',
        (encoder, decoder))


def _block_network(monkeypatch):
    monkeypatch.setattr(
        model_cache.urllib.request, 'urlopen',
        lambda *args, **kwargs: pytest.fail('backend setup must not download'))


def test_load_backend_uses_real_validated_manifest_cache(
        monkeypatch, tmp_path, small_manifest):
    """Catches bypassing cache hash validation or downloading during setup."""
    _block_network(monkeypatch)
    for artifact, payload in zip(small_manifest.artifacts, (b'enc', b'dec')):
        (tmp_path / artifact.name).write_bytes(payload)

    class FakeBackend:
        def __init__(self, encoder_path, decoder_path):
            self.paths = (encoder_path, decoder_path)

    monkeypatch.setattr(segmentation, 'OnnxSamBackend', FakeBackend)
    backend, error = segmentation.load_backend(
        {}, manifest=small_manifest, cache_dir=str(tmp_path))
    assert backend.paths == tuple(
        str(tmp_path / artifact.name) for artifact in small_manifest.artifacts)
    assert error is None


def test_load_backend_empty_real_cache_requires_setup(
        monkeypatch, tmp_path, small_manifest):
    """Catches opening the provider when the real model cache is empty."""
    _block_network(monkeypatch)
    backend, error = segmentation.load_backend(
        {}, manifest=small_manifest, cache_dir=str(tmp_path))
    assert backend is None
    assert isinstance(error, model_cache.ModelSetupRequiredError)


def test_load_backend_tampered_real_cache_requires_setup(
        monkeypatch, tmp_path, small_manifest):
    """Catches loading a real cache pair whose pinned checksum was altered."""
    _block_network(monkeypatch)
    (tmp_path / small_manifest.artifacts[0].name).write_bytes(b'bad')
    (tmp_path / small_manifest.artifacts[1].name).write_bytes(b'dec')
    backend, error = segmentation.load_backend(
        {}, manifest=small_manifest, cache_dir=str(tmp_path))
    assert backend is None
    assert isinstance(error, model_cache.ModelSetupRequiredError)
