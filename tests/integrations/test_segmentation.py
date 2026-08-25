import pytest

from libs.integrations import model_cache, segmentation
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


def test_load_backend_uses_only_validated_cached_pair(monkeypatch, tmp_path):
    """Catches backend setup calling the downloader instead of cache lookup."""
    encoder = tmp_path / 'mobile_sam.encoder.onnx'
    decoder = tmp_path / 'mobile_sam.decoder.onnx'
    cached = (str(encoder), str(decoder))
    monkeypatch.setattr(model_cache, 'cached_model_paths', lambda: cached,
                        raising=False)
    monkeypatch.setattr(
        model_cache, 'download_manifest',
        lambda *args, **kwargs: pytest.fail('backend loading must not download'),
        raising=False)

    class FakeBackend:
        def __init__(self, encoder_path, decoder_path):
            self.paths = (encoder_path, decoder_path)

    monkeypatch.setattr(segmentation, 'OnnxSamBackend', FakeBackend)
    backend, error = segmentation.load_backend({})
    assert backend.paths == cached
    assert error is None


def test_load_backend_without_cache_returns_setup_required(monkeypatch):
    """Catches implicit download when the default model cache is absent."""
    monkeypatch.setattr(model_cache, 'cached_model_paths', lambda: None,
                        raising=False)
    monkeypatch.setattr(
        model_cache, 'download_manifest',
        lambda *args, **kwargs: pytest.fail('backend loading must not download'),
        raising=False)
    backend, error = segmentation.load_backend({})
    assert backend is None
    assert isinstance(error, model_cache.ModelSetupRequiredError)
