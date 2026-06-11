import pytest

from libs.integrations.segmentation import SegmentationBackend, sam_available


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
