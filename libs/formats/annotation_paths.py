"""Deterministic paths for flat, central annotation directories.

Historically labelImg++ saved every annotation as ``<save-dir>/<image-stem>``.
That is convenient for ordinary datasets, but recursively discovered images
such as ``camera-a/frame.jpg`` and ``camera-b/frame.jpg`` overwrite each
other.  This module keeps the legacy name for unique stems and gives *every*
member of a collision group an image-specific flat stem.

Readers always try image-specific names before the legacy basename.  That
makes a collision-safe name sticky: after such a sidecar has been written,
later saves keep using it even when the active image list is narrowed.
"""
import hashlib
import os


ANNOTATION_EXTENSIONS = ('.xml', '.txt', '.json')
_DIGEST_LENGTHS = (20, 32, 48, 64)
_MAX_STEM_LENGTH = 240


def normalized_image_identity(image_path):
    """Return the stable normalized identity used to hash ``image_path``."""
    path = os.path.normcase(os.path.abspath(os.path.normpath(
        os.fspath(image_path))))
    if os.sep != '/':
        path = path.replace(os.sep, '/')
    if os.altsep:
        path = path.replace(os.altsep, '/')
    return path


def legacy_annotation_stem(image_path):
    """Return the historical annotation stem derived from the basename."""
    return os.path.splitext(os.path.basename(os.fspath(image_path)))[0]


def _hashed_stem(base_stem, digest):
    suffix = '__' + digest
    prefix_length = max(1, _MAX_STEM_LENGTH - len(suffix))
    return base_stem[:prefix_length] + suffix


def _raw_specific_stems(image_path):
    identity = normalized_image_identity(image_path)
    digest = hashlib.sha256(
        identity.encode('utf-8', errors='surrogateescape')).hexdigest()
    base_stem = legacy_annotation_stem(image_path)
    return [_hashed_stem(base_stem, digest[:length])
            for length in _DIGEST_LENGTHS]


def _active_images(image_path, image_list):
    """Return one path per normalized identity, always including the target."""
    by_identity = {}
    for path in list(image_list or []) + [image_path]:
        if not path:
            continue
        identity = normalized_image_identity(path)
        by_identity.setdefault(identity, os.fspath(path))
    return by_identity


def _valid_specific_stems(image_path, image_list=None):
    """Yield target-specific stems that cannot collide in ``image_list``.

    Prefixes are lengthened when a short hash would equal another active
    image's legacy stem or any of its possible hashed stems.  Comparing with
    all active candidates also protects case-insensitive filesystems.
    """
    target_identity = normalized_image_identity(image_path)
    active = _active_images(image_path, image_list)
    others = [path for identity, path in active.items()
              if identity != target_identity]
    forbidden = {
        legacy_annotation_stem(path).casefold()
        for path in others
    }
    for path in others:
        forbidden.update(stem.casefold()
                         for stem in _raw_specific_stems(path))

    for candidate in _raw_specific_stems(image_path):
        if candidate.casefold() not in forbidden:
            yield candidate


def image_specific_annotation_stem(image_path, image_list=None):
    """Return the shortest collision-safe stem for ``image_path``."""
    for candidate in _valid_specific_stems(image_path, image_list):
        return candidate
    # A full SHA-256 collision would be required to reach this branch.  Fail
    # explicitly instead of silently choosing an annotation path that could
    # overwrite another image.
    raise ValueError('Could not derive a unique annotation stem for %s'
                     % image_path)


def annotation_stem_candidates(image_path, image_list=None):
    """Return lookup stems ordered image-specific first, then legacy."""
    candidates = list(_valid_specific_stems(image_path, image_list))
    legacy = legacy_annotation_stem(image_path)
    if legacy.casefold() not in {stem.casefold() for stem in candidates}:
        candidates.append(legacy)
    return candidates


def _has_active_legacy_collision(image_path, image_list):
    target_identity = normalized_image_identity(image_path)
    target_stem = legacy_annotation_stem(image_path).casefold()
    for identity, path in _active_images(image_path, image_list).items():
        if identity == target_identity:
            continue
        if legacy_annotation_stem(path).casefold() == target_stem:
            return True
    return False


def _stem_has_annotation(save_dir, stem, extensions=ANNOTATION_EXTENSIONS):
    if not save_dir:
        return False
    return any(os.path.isfile(os.path.join(os.fspath(save_dir), stem + ext))
               for ext in extensions)


def annotation_output_stem(image_path, save_dir, image_list=None,
                           resolver=None):
    """Choose the flat output stem for an image.

    An existing image-specific sidecar takes precedence so its name remains
    stable when the active list changes.  Otherwise the specific stem is used
    only for a current case-insensitive basename collision.
    """
    if resolver is not None:
        return resolver.output_stem(image_path)

    specific_stems = list(_valid_specific_stems(image_path, image_list))
    for stem in specific_stems:
        if _stem_has_annotation(save_dir, stem):
            return stem
    if _has_active_legacy_collision(image_path, image_list):
        if not specific_stems:
            raise ValueError('Could not derive a unique annotation stem for %s'
                             % image_path)
        return specific_stems[0]
    return legacy_annotation_stem(image_path)


def annotation_output_base(image_path, save_dir, image_list=None,
                           resolver=None):
    """Return the extension-less path used for a central annotation save."""
    return os.path.join(
        os.fspath(save_dir),
        annotation_output_stem(
            image_path, save_dir, image_list, resolver=resolver),
    )


def annotation_path_candidates(image_path, extension, save_dir=None,
                               image_list=None, resolver=None):
    """Return sidecar paths ordered specific-first and legacy-last.

    For each stem the central save directory is preferred, followed by the
    original image directory.  Duplicate directory spellings are removed.
    """
    if resolver is not None:
        return list(resolver.path_candidates(image_path, extension))

    if not extension.startswith('.'):
        extension = '.' + extension

    directories = []
    if save_dir:
        directories.append(os.fspath(save_dir))
    directories.append(os.path.dirname(os.fspath(image_path)))

    unique_directories = []
    seen_directories = set()
    for directory in directories:
        identity = os.path.normcase(os.path.abspath(os.path.normpath(
            directory or os.curdir)))
        if identity not in seen_directories:
            seen_directories.add(identity)
            unique_directories.append(directory)

    paths = []
    for stem in annotation_stem_candidates(image_path, image_list):
        for directory in unique_directories:
            paths.append(os.path.join(directory, stem + extension))
    return paths


def find_existing_annotation(image_path, save_dir=None, image_list=None,
                             extensions=ANNOTATION_EXTENSIONS, resolver=None):
    """Return the first existing specific/legacy annotation sidecar."""
    if resolver is not None:
        return resolver.find_existing(image_path, extensions=extensions)

    stems = annotation_stem_candidates(image_path, image_list)
    directories = []
    if save_dir:
        directories.append(os.fspath(save_dir))
    image_dir = os.path.dirname(os.fspath(image_path))
    if not directories or os.path.normcase(os.path.abspath(image_dir)) != \
            os.path.normcase(os.path.abspath(directories[0])):
        directories.append(image_dir)

    for stem in stems:
        for extension in extensions:
            if not extension.startswith('.'):
                extension = '.' + extension
            for directory in directories:
                path = os.path.join(directory, stem + extension)
                if os.path.isfile(path):
                    return path
    return None
