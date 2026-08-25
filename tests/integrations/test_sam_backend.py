# tests/integrations/test_sam_backend.py
import os

import pytest

from libs.core.assist_state import AssistPrompt
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
    mask = backend.predict(AssistPrompt(
        mode='points', positive_points=((50.0, 35.0),)))
    assert mask.dtype == bool
    assert mask.shape == (64, 96)
    assert mask[35, 50]                               # clicked pixel is masked
    assert backend.model_loaded and backend.image_is_set


class _RecordingDecoder:
    def __init__(self, numpy):
        self.numpy = numpy
        self.feeds = []

    def run(self, _names, feeds):
        self.feeds.append(feeds)
        return (
            self.numpy.zeros((1, 1, 12, 16), dtype=self.numpy.float32),
            self.numpy.zeros((1, 1), dtype=self.numpy.float32),
            self.numpy.zeros((1, 1, 256, 256), dtype=self.numpy.float32),
        )


def _recording_backend(numpy):
    backend = segmentation.OnnxSamBackend.__new__(
        segmentation.OnnxSamBackend)
    backend._embeddings = numpy.zeros((1, 256, 64, 64), dtype=numpy.float32)
    backend._orig_size = (12, 16)
    backend._scale = (2.0, 3.0)
    backend._decoder = _RecordingDecoder(numpy)
    backend._model_loaded = True
    return backend


def test_points_prompt_maps_positive_negative_and_padding_labels():
    """Catches losing negative refinement or SAM point-prompt padding."""
    numpy = pytest.importorskip('numpy')
    backend = _recording_backend(numpy)

    backend.predict(AssistPrompt(
        mode='points',
        positive_points=((1.0, 2.0), (3.0, 4.0)),
        negative_points=((5.0, 6.0),)))

    feeds = backend._decoder.feeds[-1]
    assert feeds['point_coords'].tolist() == [[
        [2.0, 6.0], [6.0, 12.0], [10.0, 18.0], [0.0, 0.0]]]
    assert feeds['point_labels'].tolist() == [[1.0, 1.0, 0.0, -1.0]]


def test_box_prompt_maps_corners_without_padding_point():
    """Catches encoding a box as ordinary clicks or appending point padding."""
    numpy = pytest.importorskip('numpy')
    backend = _recording_backend(numpy)

    backend.predict(AssistPrompt(
        mode='box', box=(1.0, 2.0, 30.0, 40.0)))

    feeds = backend._decoder.feeds[-1]
    assert feeds['point_coords'].tolist() == [[
        [2.0, 6.0], [60.0, 120.0]]]
    assert feeds['point_labels'].tolist() == [[2.0, 3.0]]
