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


CUDA_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]
CUDNN_ERROR = "LoadLibrary failed for cudnn64_9.dll with error 2"


@pytest.fixture
def fake_ort(monkeypatch):
    """Patch onnxruntime with sessions whose failures are per-provider."""
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    ort = pytest.importorskip("onnxruntime")

    class _FakeSession:
        def __init__(self, path, providers):
            self.path = path
            self.providers = list(providers)
            self.runs = 0

        def get_providers(self):
            return list(self.providers)

        def run(self, names, feeds):
            self.runs += 1
            if (self.providers[0], self.path) in state["run_failures"]:
                raise RuntimeError(CUDNN_ERROR)
            if "input_image" in feeds:
                return [np.zeros((1, 256, 64, 64), dtype=np.float32)]
            h, w = (int(v) for v in feeds["orig_im_size"])
            return [np.ones((1, 1, h, w), dtype=np.float32), None, None]

    def _session(path, providers):
        if (providers[0], path) in state["create_failures"]:
            raise RuntimeError(CUDNN_ERROR)
        session = _FakeSession(path, providers)
        state["sessions"].append(session)
        return session

    state = {"sessions": [], "run_failures": set(), "create_failures": set()}
    monkeypatch.setattr(ort, "get_available_providers", lambda: CUDA_PROVIDERS)
    monkeypatch.setattr(ort, "InferenceSession", _session)
    return state


def test_set_image_falls_back_to_cpu_when_cuda_run_fails(fake_ort):
    np = pytest.importorskip("numpy")
    from libs.integrations.segmentation import OnnxSamBackend
    fake_ort["run_failures"].add(("CUDAExecutionProvider", "enc.onnx"))

    backend = OnnxSamBackend("enc.onnx", "dec.onnx")
    backend.set_image(np.zeros((64, 96, 3), dtype=np.uint8))
    mask = backend.predict([(50, 35)], [1])

    assert backend.image_is_set
    assert mask.dtype == bool and mask.shape == (64, 96) and mask.all()
    assert backend._encoder.get_providers() == ["CPUExecutionProvider"]
    assert backend._decoder.get_providers() == ["CPUExecutionProvider"]


def test_predict_falls_back_to_cpu_and_keeps_embedding(fake_ort):
    np = pytest.importorskip("numpy")
    from libs.integrations.segmentation import OnnxSamBackend
    fake_ort["run_failures"].add(("CUDAExecutionProvider", "dec.onnx"))

    backend = OnnxSamBackend("enc.onnx", "dec.onnx")
    backend.set_image(np.zeros((64, 96, 3), dtype=np.uint8))
    cuda_encoder = backend._encoder
    mask = backend.predict([(50, 35)], [1])

    assert mask.shape == (64, 96) and mask.all()
    assert cuda_encoder.runs == 1
    assert backend._encoder.runs == 0                 # embedding was reused
    assert backend._decoder.get_providers() == ["CPUExecutionProvider"]


def test_session_creation_falls_back_to_cpu(fake_ort):
    from libs.integrations.segmentation import OnnxSamBackend
    fake_ort["create_failures"].add(("CUDAExecutionProvider", "dec.onnx"))

    backend = OnnxSamBackend("enc.onnx", "dec.onnx")

    assert backend._encoder.get_providers() == ["CPUExecutionProvider"]
    assert backend._decoder.get_providers() == ["CPUExecutionProvider"]


def test_cpu_run_failure_is_raised_without_retry(fake_ort, monkeypatch):
    np = pytest.importorskip("numpy")
    import onnxruntime as ort
    from libs.integrations.segmentation import OnnxSamBackend
    monkeypatch.setattr(ort, "get_available_providers",
                        lambda: ["CPUExecutionProvider"])
    fake_ort["run_failures"].add(("CPUExecutionProvider", "enc.onnx"))

    backend = OnnxSamBackend("enc.onnx", "dec.onnx")
    with pytest.raises(RuntimeError, match="cudnn64_9"):
        backend.set_image(np.zeros((64, 96, 3), dtype=np.uint8))
    assert len(fake_ort["sessions"]) == 2
