# libs/integrations/model_cache.py
"""Resolve the SAM ONNX model pair: explicit settings paths win, otherwise
self-hosted MobileSAM encoder/decoder artifacts are downloaded on first use
and SHA256-verified.

No new runtime dependency (stdlib urllib + hashlib). SHA256 pinning protects
the integrity of the downloaded artifacts.
"""

import hashlib
import os
import urllib.request

from libs.utils.constants import SETTING_SAM_DECODER, SETTING_SAM_ENCODER

# ONNX encoder/decoder pair hosted as GitHub Release assets (tag sam-onnx-v1).
# Exported from the official mobile_sam.pt by scripts/export_sam_onnx.py.
MOBILE_SAM_ENCODER_URL = (
    "https://github.com/abhiksark/labelImg-plus-plus/releases/download/"
    "sam-onnx-v1/mobile_sam.encoder.onnx"
)
MOBILE_SAM_ENCODER_SHA256 = (
    "801d81952ee19217632966f7cfe07a8030c115a7fe5bfbec9294bfaf95e44a45")
MOBILE_SAM_DECODER_URL = (
    "https://github.com/abhiksark/labelImg-plus-plus/releases/download/"
    "sam-onnx-v1/mobile_sam.decoder.onnx"
)
MOBILE_SAM_DECODER_SHA256 = (
    "001f6386a4c6036f6fac6a104d18d7c008c7eb188b2936dab749e34cae33e1c8")
_CHUNK = 1 << 20


def _cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "labelimgpp")
    os.makedirs(path, exist_ok=True)
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url, dest, expected_sha, progress):
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(url) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            read = 0
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                read += len(chunk)
                if progress:
                    progress(read, total)
        if expected_sha and _sha256(tmp) != expected_sha:
            raise ValueError("SAM model SHA256 mismatch; download discarded")
        os.replace(tmp, dest)
        return dest
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def default_model_paths():
    cache = _cache_dir()
    return (os.path.join(cache, "mobile_sam.encoder.onnx"),
            os.path.join(cache, "mobile_sam.decoder.onnx"))


def _resolve_one(url, dest, expected_sha, progress):
    # An empty pin disables verification (mirrors _download's contract); the
    # shipped ONNX pins are always filled — see test_onnx_pins_are_filled.
    if os.path.isfile(dest) and (
            not expected_sha or _sha256(dest) == expected_sha):
        return dest
    return _download(url, dest, expected_sha, progress)


def resolve_models(settings, progress=None):
    """Return (encoder_path, decoder_path), downloading defaults if needed.

    Explicit user-set paths are trusted as-is but must come as a pair: a
    custom encoder produces embeddings the default decoder cannot read, so a
    half-set pair is an error rather than a silent mismatch. Auto-downloaded
    defaults are re-verified against their pins on every use.
    """
    encoder = settings.get(SETTING_SAM_ENCODER, "")
    decoder = settings.get(SETTING_SAM_DECODER, "")
    if encoder or decoder:
        if not (encoder and decoder):
            raise ValueError(
                "both encoder and decoder paths are required"
                " for a custom model")
        for path in (encoder, decoder):
            if not os.path.isfile(path):
                raise ValueError("SAM model file not found: %s" % path)
        return encoder, decoder
    enc_dest, dec_dest = default_model_paths()
    return (
        _resolve_one(MOBILE_SAM_ENCODER_URL, enc_dest,
                     MOBILE_SAM_ENCODER_SHA256, progress),
        _resolve_one(MOBILE_SAM_DECODER_URL, dec_dest,
                     MOBILE_SAM_DECODER_SHA256, progress),
    )
