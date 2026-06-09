# libs/integrations/model_cache.py
"""Resolve the SAM checkpoint path: explicit settings path wins, otherwise
download a self-hosted MobileSAM weight on first use and SHA256-verify it.

No new runtime dependency (stdlib urllib + hashlib). SHA256 pinning is the
primary code-execution-risk mitigation for the pickle a checkpoint contains.
"""

import hashlib
import os
import urllib.request

from libs.utils.constants import SETTING_SAM_CHECKPOINT

# Self-hosted GitHub Release asset. Fill MOBILE_SAM_SHA256 after uploading the
# asset:  sha256sum mobile_sam.pt
MOBILE_SAM_URL = (
    "https://github.com/abhiksark/labelImg-plus-plus/releases/download/"
    "sam-weights-v1/mobile_sam.pt"
)
# REQUIRED: paste the asset's sha256 here before release (left empty until then)
MOBILE_SAM_SHA256 = ""
_CHUNK = 1 << 20


def _cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "labelimgpp")
    os.makedirs(path, exist_ok=True)
    return path


def default_checkpoint_path():
    return os.path.join(_cache_dir(), "mobile_sam.pt")


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
            raise ValueError("SAM checkpoint SHA256 mismatch; download discarded")
        os.replace(tmp, dest)
        return dest
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def resolve_checkpoint(settings, progress=None):
    """Return a local checkpoint path, downloading the default if needed.

    An explicit user-set path is trusted as-is. The auto-downloaded default is
    re-verified against MOBILE_SAM_SHA256 on every use, so a file cached while
    the pin was still empty gets re-fetched once the real digest is in place.
    """
    path = settings.get(SETTING_SAM_CHECKPOINT, "")
    if path and os.path.isfile(path):
        return path
    dest = default_checkpoint_path()
    if os.path.isfile(dest) and (
            not MOBILE_SAM_SHA256 or _sha256(dest) == MOBILE_SAM_SHA256):
        return dest
    return _download(MOBILE_SAM_URL, dest, MOBILE_SAM_SHA256, progress)
