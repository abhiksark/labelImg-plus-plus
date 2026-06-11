# tests/integrations/test_model_cache.py
import hashlib
import os

import pytest

from libs.integrations import model_cache
from libs.utils.constants import SETTING_SAM_CHECKPOINT, SETTING_SAM_ENCODER, SETTING_SAM_DECODER


class _Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def test_explicit_path_short_circuits_download(tmp_path, monkeypatch):
    ckpt = tmp_path / "my.pt"
    ckpt.write_bytes(b"weights")
    called = {"download": False}
    monkeypatch.setattr(model_cache, "_download",
                        lambda *a, **k: called.__setitem__("download", True))
    settings = _Settings({SETTING_SAM_CHECKPOINT: str(ckpt)})
    assert model_cache.resolve_checkpoint(settings) == str(ckpt)
    assert called["download"] is False


def test_sha256_mismatch_is_rejected(tmp_path, monkeypatch):
    payload = b"not-the-real-weights"

    class _Resp:
        headers = {"Content-Length": str(len(payload))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return payload

    monkeypatch.setattr(model_cache.urllib.request, "urlopen", lambda url: _Resp())
    dest = tmp_path / "mobile_sam.pt"
    with pytest.raises(ValueError, match="SHA256"):
        model_cache._download("http://x", str(dest), "deadbeef", None)
    assert not dest.exists()           # .part cleaned up, nothing renamed in


def test_download_succeeds_when_sha_matches(tmp_path, monkeypatch):
    payload = b"real-weights"
    good = hashlib.sha256(payload).hexdigest()

    class _Resp:
        headers = {"Content-Length": str(len(payload))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return payload

    monkeypatch.setattr(model_cache.urllib.request, "urlopen", lambda url: _Resp())
    dest = tmp_path / "mobile_sam.pt"
    out = model_cache._download("http://x", str(dest), good, None)
    assert out == str(dest) and dest.read_bytes() == payload


def test_cached_default_short_circuits_when_pin_empty(tmp_path, monkeypatch):
    dest = tmp_path / "mobile_sam.pt"
    dest.write_bytes(b"cached")
    monkeypatch.setattr(model_cache, "default_checkpoint_path", lambda: str(dest))
    monkeypatch.setattr(model_cache, "MOBILE_SAM_SHA256", "")
    called = {"download": False}
    monkeypatch.setattr(model_cache, "_download",
                        lambda *a, **k: called.__setitem__("download", True))
    assert model_cache.resolve_checkpoint(_Settings()) == str(dest)
    assert called["download"] is False


def test_cached_default_refetched_when_pin_mismatches(tmp_path, monkeypatch):
    dest = tmp_path / "mobile_sam.pt"
    dest.write_bytes(b"stale-weights")
    monkeypatch.setattr(model_cache, "default_checkpoint_path", lambda: str(dest))
    monkeypatch.setattr(model_cache, "MOBILE_SAM_SHA256", "f" * 64)   # won't match
    called = {"download": False}
    monkeypatch.setattr(
        model_cache, "_download",
        lambda *a, **k: called.__setitem__("download", True) or "redownloaded")
    assert model_cache.resolve_checkpoint(_Settings()) == "redownloaded"
    assert called["download"] is True


def test_download_with_empty_sha_skips_verification(tmp_path, monkeypatch):
    payload = b"unverified"

    class _Resp:
        headers = {"Content-Length": str(len(payload))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return payload

    monkeypatch.setattr(model_cache.urllib.request, "urlopen", lambda url: _Resp())
    dest = tmp_path / "mobile_sam.pt"
    out = model_cache._download("http://x", str(dest), "", None)
    assert out == str(dest) and dest.read_bytes() == payload


def test_resolve_models_custom_pair_short_circuits(tmp_path, monkeypatch):
    enc = tmp_path / "e.onnx"
    dec = tmp_path / "d.onnx"
    enc.write_bytes(b"e")
    dec.write_bytes(b"d")
    called = {"download": False}
    monkeypatch.setattr(model_cache, "_download",
                        lambda *a, **k: called.__setitem__("download", True))
    settings = _Settings({SETTING_SAM_ENCODER: str(enc),
                          SETTING_SAM_DECODER: str(dec)})
    assert model_cache.resolve_models(settings) == (str(enc), str(dec))
    assert called["download"] is False


def test_resolve_models_half_pair_rejected(tmp_path):
    enc = tmp_path / "e.onnx"
    enc.write_bytes(b"e")
    with pytest.raises(ValueError, match="both encoder and decoder"):
        model_cache.resolve_models(_Settings({SETTING_SAM_ENCODER: str(enc)}))


def test_resolve_models_missing_custom_file_rejected(tmp_path):
    settings = _Settings({SETTING_SAM_ENCODER: str(tmp_path / "no-e.onnx"),
                          SETTING_SAM_DECODER: str(tmp_path / "no-d.onnx")})
    with pytest.raises(ValueError, match="not found"):
        model_cache.resolve_models(settings)


def test_resolve_models_uses_verified_cache(tmp_path, monkeypatch):
    enc = tmp_path / "mobile_sam.encoder.onnx"
    dec = tmp_path / "mobile_sam.decoder.onnx"
    enc.write_bytes(b"enc")
    dec.write_bytes(b"dec")
    monkeypatch.setattr(model_cache, "default_model_paths",
                        lambda: (str(enc), str(dec)))
    monkeypatch.setattr(model_cache, "MOBILE_SAM_ENCODER_SHA256",
                        hashlib.sha256(b"enc").hexdigest())
    monkeypatch.setattr(model_cache, "MOBILE_SAM_DECODER_SHA256",
                        hashlib.sha256(b"dec").hexdigest())
    called = {"download": False}
    monkeypatch.setattr(model_cache, "_download",
                        lambda *a, **k: called.__setitem__("download", True))
    assert model_cache.resolve_models(_Settings()) == (str(enc), str(dec))
    assert called["download"] is False


def test_resolve_models_refetches_stale_artifact(tmp_path, monkeypatch):
    enc = tmp_path / "mobile_sam.encoder.onnx"
    dec = tmp_path / "mobile_sam.decoder.onnx"
    enc.write_bytes(b"stale")
    dec.write_bytes(b"dec")
    monkeypatch.setattr(model_cache, "default_model_paths",
                        lambda: (str(enc), str(dec)))
    monkeypatch.setattr(model_cache, "MOBILE_SAM_ENCODER_SHA256", "f" * 64)
    monkeypatch.setattr(model_cache, "MOBILE_SAM_DECODER_SHA256",
                        hashlib.sha256(b"dec").hexdigest())
    downloads = []
    monkeypatch.setattr(
        model_cache, "_download",
        lambda url, dest, sha, progress: downloads.append(dest) or dest)
    encoder, decoder = model_cache.resolve_models(_Settings())
    assert downloads == [str(enc)]      # only the stale artifact re-fetched
    assert (encoder, decoder) == (str(enc), str(dec))


def test_onnx_pins_are_filled():
    assert len(model_cache.MOBILE_SAM_ENCODER_SHA256) == 64
    assert len(model_cache.MOBILE_SAM_DECODER_SHA256) == 64


def test_resolve_one_empty_pin_reuses_cache_without_download(tmp_path,
                                                              monkeypatch):
    dest = tmp_path / "mobile_sam.encoder.onnx"
    dest.write_bytes(b"cached")
    called = {"download": False}
    monkeypatch.setattr(model_cache, "_download",
                        lambda *a, **k: called.__setitem__("download", True))
    assert model_cache._resolve_one("http://x", str(dest), "", None) == str(dest)
    assert called["download"] is False


def test_resolve_models_forwards_progress_to_download(tmp_path, monkeypatch):
    enc = tmp_path / "mobile_sam.encoder.onnx"     # neither file exists yet
    dec = tmp_path / "mobile_sam.decoder.onnx"
    monkeypatch.setattr(model_cache, "default_model_paths",
                        lambda: (str(enc), str(dec)))
    seen = []
    monkeypatch.setattr(
        model_cache, "_download",
        lambda url, dest, sha, progress: seen.append(progress) or dest)
    sentinel = object()
    model_cache.resolve_models(_Settings(), progress=sentinel)
    assert seen == [sentinel, sentinel]
