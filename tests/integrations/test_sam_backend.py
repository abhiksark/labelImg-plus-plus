# tests/integrations/test_sam_backend.py
import os

import pytest

from libs.integrations import segmentation, model_cache


def test_load_backend_reports_checkpoint_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(model_cache, "resolve_checkpoint", boom)
    backend, err = segmentation.load_backend({})
    assert backend is None
    assert err and "network" in err.lower()


def test_load_backend_reports_model_load_error(monkeypatch, tmp_path):
    ckpt = tmp_path / "m.pt"
    ckpt.write_bytes(b"x")
    monkeypatch.setattr(model_cache, "resolve_checkpoint", lambda *a, **k: str(ckpt))

    def boom(*a, **k):
        raise RuntimeError("bad model")
    monkeypatch.setattr(segmentation, "SamBackend", boom)
    backend, err = segmentation.load_backend({})
    assert backend is None
    assert err and "load" in err.lower()


def test_sam_backend_predict_real():
    pytest.importorskip("torch")
    pytest.importorskip("mobile_sam")
    np = pytest.importorskip("numpy")
    ckpt = os.environ.get("SAM_TEST_CHECKPOINT")
    if not ckpt or not os.path.isfile(ckpt):
        pytest.skip("set SAM_TEST_CHECKPOINT to a local mobile_sam.pt to run")
    from libs.integrations.segmentation import SamBackend
    backend = SamBackend(ckpt, model_type="vit_t", device="cpu")
    rgb = np.zeros((64, 64, 3), dtype=np.uint8)
    rgb[20:50, 20:50] = 255
    backend.set_image(rgb)
    mask = backend.predict([(35, 35)], [1])
    assert mask.dtype == bool
    assert mask.shape == (64, 64)
    assert backend.model_loaded and backend.image_is_set
