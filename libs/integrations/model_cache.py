"""Validated local cache and explicit downloads for Assist model artifacts.

Model resolution never performs network I/O.  The Assist download action owns
the only acquisition path through :func:`download_manifest`.
"""

import hashlib
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

from libs.integrations.model_manifest import MOBILE_SAM_MANIFEST
from libs.utils.constants import SETTING_SAM_DECODER, SETTING_SAM_ENCODER

_HASH_CHUNK = 1 << 20
_DOWNLOAD_CHUNK = 64 * 1024
# Allows finite CDN/TLS/read idle gaps while still bounding cancellation to one
# socket operation. Tests and callers may supply a shorter explicit timeout.
DEFAULT_DOWNLOAD_TIMEOUT = 10.0


@dataclass(frozen=True)
class ModelDownloadProgress:
    """Current artifact bytes and manifest-complete bytes.

    ``downloaded`` counts network bytes received for ``artifact``.  Reused
    validated final artifacts contribute to ``total_downloaded`` so callers
    can truthfully render overall manifest completion on explicit retry.
    """
    artifact: str
    downloaded: int
    artifact_size: int
    total_downloaded: int
    total_size: int


class ModelDownloadCancelled(Exception):
    pass


class ModelOfflineError(RuntimeError):
    pass


class ModelProviderError(RuntimeError):
    pass


class ModelValidationError(RuntimeError):
    pass


class ModelSetupRequiredError(RuntimeError):
    pass


def _cache_dir():
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(
        os.path.expanduser('~'), '.cache')
    path = os.path.join(base, 'labelimgpp')
    os.makedirs(path, exist_ok=True)
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_cached(path, artifact):
    return (os.path.isfile(path) and os.path.getsize(path) == artifact.size
            and _sha256(path) == artifact.sha256)


def _raise_network_error(error, cancelled):
    if cancelled and cancelled():
        raise ModelDownloadCancelled()
    raise ModelOfflineError(str(error))


def default_model_paths():
    """Return the conventional MobileSAM cache locations."""
    cache = _cache_dir()
    return tuple(os.path.join(cache, item.name)
                 for item in MOBILE_SAM_MANIFEST.artifacts)


def cached_model_paths(manifest=MOBILE_SAM_MANIFEST, cache_dir=None):
    """Return fully validated artifact paths, or ``None`` when setup is needed."""
    root = cache_dir or _cache_dir()
    paths = tuple(os.path.join(root, item.name) for item in manifest.artifacts)
    if all(_valid_cached(path, artifact)
           for path, artifact in zip(paths, manifest.artifacts)):
        return paths
    return None


def download_manifest(manifest, cache_dir, cancelled=None, progress=None,
                      timeout=DEFAULT_DOWNLOAD_TIMEOUT):
    """Download, validate, and atomically promote every manifest artifact.

    ``timeout`` bounds urllib's connection and response socket operations.
    Existing final artifacts are reused only after manifest validation. There
    is deliberately no retry loop: callers decide whether to try again.
    """
    os.makedirs(cache_dir, exist_ok=True)
    outputs = []
    targets = []
    for artifact in manifest.artifacts:
        destination = os.path.join(cache_dir, artifact.name)
        temporary = destination + '.part'
        if os.path.exists(temporary):
            os.unlink(temporary)
        reusable = _valid_cached(destination, artifact)
        targets.append((artifact, destination, temporary, reusable))

    total_downloaded = sum(
        artifact.size for artifact, _destination, _temporary, reusable
        in targets if reusable)
    for artifact, destination, temporary, reusable in targets:
        if reusable:
            outputs.append(destination)
            continue
        try:
            with urllib.request.urlopen(
                    artifact.url, timeout=timeout) as response, \
                    open(temporary, 'wb') as output:
                try:
                    header_size = int(response.headers.get('Content-Length') or 0)
                except (TypeError, ValueError):
                    raise ModelValidationError(
                        'provider size does not match manifest')
                if header_size and header_size != artifact.size:
                    raise ModelValidationError(
                        'provider size does not match manifest')
                digest = hashlib.sha256()
                artifact_bytes = 0
                while True:
                    if cancelled and cancelled():
                        raise ModelDownloadCancelled()
                    chunk = response.read(_DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    artifact_bytes += len(chunk)
                    if artifact_bytes > artifact.size:
                        raise ModelValidationError(
                            'download size does not match manifest')
                    total_downloaded += len(chunk)
                    if progress:
                        progress(ModelDownloadProgress(
                            artifact.name, artifact_bytes, artifact.size,
                            total_downloaded, manifest.total_size))
                if artifact_bytes != artifact.size:
                    raise ModelValidationError(
                        'download size does not match manifest')
                if digest.hexdigest() != artifact.sha256:
                    raise ModelValidationError(
                        'download checksum does not match manifest')
                output.flush()
                os.fsync(output.fileno())
            if cancelled and cancelled():
                raise ModelDownloadCancelled()
            os.replace(temporary, destination)
            outputs.append(destination)
        except urllib.error.HTTPError as exc:
            if cancelled and cancelled():
                raise ModelDownloadCancelled()
            raise ModelProviderError(str(exc))
        except (socket.timeout, TimeoutError) as exc:
            _raise_network_error(exc, cancelled)
        except urllib.error.URLError as exc:
            _raise_network_error(exc, cancelled)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return tuple(outputs)


def resolve_models(settings, progress=None, manifest=MOBILE_SAM_MANIFEST,
                   cache_dir=None):
    """Resolve custom paths or a validated default cache without downloading.

    ``progress`` remains accepted for extensions using the old call shape, but
    is intentionally unused: progress belongs to ``download_manifest``.
    """
    encoder = settings.get(SETTING_SAM_ENCODER, '')
    decoder = settings.get(SETTING_SAM_DECODER, '')
    if encoder or decoder:
        if not (encoder and decoder):
            raise ValueError(
                'both encoder and decoder paths are required for a custom model')
        for path in (encoder, decoder):
            if not os.path.isfile(path):
                raise ValueError('SAM model file not found: %s' % path)
        return encoder, decoder
    paths = cached_model_paths(manifest, cache_dir)
    if paths is None:
        raise ModelSetupRequiredError(
            'SAM model setup is required; download MobileSAM before using Assist')
    return paths
