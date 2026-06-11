# tests/integrations/test_sam_backend.py
import os

import pytest

from libs.integrations import segmentation, model_cache


def test_load_backend_reports_model_files_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(model_cache, "resolve_models", boom)
    backend, err = segmentation.load_backend({})
    assert backend is None
    assert err and "obtain" in err.lower() and "network" in err.lower()


def test_load_backend_reports_model_load_error(monkeypatch, tmp_path):
    enc = tmp_path / "e.onnx"
    dec = tmp_path / "d.onnx"
    enc.write_bytes(b"x")
    dec.write_bytes(b"x")
    monkeypatch.setattr(model_cache, "resolve_models",
                        lambda *a, **k: (str(enc), str(dec)))

    def boom(*a, **k):
        raise RuntimeError("bad model")
    monkeypatch.setattr(segmentation, "OnnxSamBackend", boom)
    backend, err = segmentation.load_backend({})
    assert backend is None
    assert err and "load" in err.lower()


def test_onnx_backend_predict_real():
    pytest.importorskip("onnxruntime")
    pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    enc = os.environ.get("SAM_TEST_ENCODER")
    dec = os.environ.get("SAM_TEST_DECODER")
    if not (enc and dec and os.path.isfile(enc) and os.path.isfile(dec)):
        pytest.skip("set SAM_TEST_ENCODER/SAM_TEST_DECODER to local .onnx files")
    from libs.integrations.segmentation import OnnxSamBackend
    backend = OnnxSamBackend(enc, dec)
    rgb = np.zeros((64, 96, 3), dtype=np.uint8)      # non-square: checks scaling
    rgb[20:50, 30:70] = 255
    backend.set_image(rgb)
    mask = backend.predict([(50, 35)], [1])
    assert mask.dtype == bool
    assert mask.shape == (64, 96)
    assert mask[35, 50]                               # clicked pixel is masked
    assert backend.model_loaded and backend.image_is_set
