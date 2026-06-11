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
