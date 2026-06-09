# tests/integrations/test_model_cache.py
import hashlib
import os

import pytest

from libs.integrations import model_cache
from libs.utils.constants import SETTING_SAM_CHECKPOINT


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
