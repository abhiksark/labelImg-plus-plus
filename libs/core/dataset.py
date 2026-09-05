"""Immutable dataset snapshots and linear-time annotation path indexing.

The public helpers in :mod:`libs.formats.annotation_paths` intentionally keep
their historical list-based API.  Passing a complete image list to those
helpers for every image is quadratic, though: every lookup rebuilds the same
collision information.  This module computes that information once and keeps
directory contents in immutable filename sets so catalog scans do not issue a
series of ``isfile`` calls for every image.
"""

from dataclasses import dataclass, replace
from types import MappingProxyType
import os
import time

from libs.formats.annotation_paths import (
    ANNOTATION_EXTENSIONS,
    _raw_specific_stems,
    legacy_annotation_stem,
    normalized_image_identity,
)
from libs.utils.utils import natural_sort


def _directory_identity(path):
    return os.path.normcase(os.path.abspath(os.path.normpath(
        os.fspath(path) if path else os.curdir)))


def _unique_directories(image_path, save_dir):
    directories = []
    if save_dir:
        directories.append(os.fspath(save_dir))
    directories.append(os.path.dirname(os.fspath(image_path)))
    result = []
    seen = set()
    for directory in directories:
        identity = _directory_identity(directory)
        if identity not in seen:
            seen.add(identity)
            result.append(directory)
    return tuple(result)


def _scan_files(directory):
    """Return regular filenames in *directory* without following failures."""
    names = set()
    try:
        with os.scandir(directory or os.curdir) as entries:
            for entry in entries:
                try:
                    if entry.is_file():
                        names.add(entry.name)
                except OSError:
                    continue
    except OSError:
        pass
    return frozenset(names)


class AnnotationResolver:
    """Precomputed annotation naming and directory index for one dataset."""

    def __init__(self, image_paths, save_dir=None, directory_files=None):
        self.image_paths = tuple(image_paths)
        self.save_dir = os.fspath(save_dir) if save_dir else None

        # Match annotation_paths._active_images: one path per normalized
        # identity, preserving first occurrence.
        by_identity = {}
        for path in self.image_paths:
            if path:
                by_identity.setdefault(
                    normalized_image_identity(path), os.fspath(path))
        self._by_identity = MappingProxyType(by_identity)

        legacy_by_identity = {
            identity: legacy_annotation_stem(path)
            for identity, path in by_identity.items()
        }
        raw_by_identity = {
            identity: tuple(_raw_specific_stems(path))
            for identity, path in by_identity.items()
        }

        # A candidate is valid iff no *other* image owns its case-folded token
        # as either a legacy or possible hashed stem.  Building token owners
        # once makes all candidate selection O(n), rather than O(n^2).
        token_owners = {}
        legacy_owners = {}
        for identity, legacy in legacy_by_identity.items():
            legacy_owners.setdefault(legacy.casefold(), set()).add(identity)
            token_owners.setdefault(legacy.casefold(), set()).add(identity)
            for stem in raw_by_identity[identity]:
                token_owners.setdefault(stem.casefold(), set()).add(identity)

        candidates = {}
        collision = {}
        for identity, path in by_identity.items():
            valid = tuple(
                stem for stem in raw_by_identity[identity]
                if token_owners.get(stem.casefold(), set()) <= {identity}
            )
            if not valid:
                raise ValueError(
                    'Could not derive a unique annotation stem for %s' % path)
            legacy = legacy_by_identity[identity]
            if legacy.casefold() not in {s.casefold() for s in valid}:
                valid += (legacy,)
            candidates[identity] = valid
            collision[identity] = len(
                legacy_owners.get(legacy.casefold(), ())) > 1

        self._candidates = MappingProxyType(candidates)
        self._collisions = MappingProxyType(collision)

        if directory_files is None:
            directories = {}
            for path in by_identity.values():
                for directory in _unique_directories(path, self.save_dir):
                    directories.setdefault(
                        _directory_identity(directory), directory)
                # The annotation probe also supports the conventional YOLO
                # sibling labels directory.
                image_dir = os.path.dirname(path)
                labels_dir = os.path.join(
                    os.path.dirname(image_dir), 'labels')
                directories.setdefault(
                    _directory_identity(labels_dir), labels_dir)
            indexed = {
                identity: _scan_files(directory)
                for identity, directory in directories.items()
            }
        else:
            indexed = {
                _directory_identity(directory): frozenset(names)
                for directory, names in directory_files.items()
            }
        self._directory_files = MappingProxyType(indexed)
        directory_groups = {}
        directories_by_identity = {}
        for identity, path in by_identity.items():
            directories = tuple(_unique_directories(path, self.save_dir))
            directories = directory_groups.setdefault(
                directories, directories)
            directories_by_identity[identity] = directories
        self._directories_by_identity = MappingProxyType(
            directories_by_identity)

        available_by_identity = {}
        conventional_yolo = {}
        for identity, path in by_identity.items():
            available_by_identity[identity] = self._available_for_identity(
                identity, indexed)
            image_dir = os.path.dirname(path)
            labels_dir = os.path.join(os.path.dirname(image_dir), 'labels')
            yolo_path = os.path.join(
                labels_dir, legacy_annotation_stem(path) + '.txt')
            names = indexed.get(_directory_identity(labels_dir), ())
            conventional_yolo[identity] = (
                yolo_path if os.path.basename(yolo_path) in names else None)
        self._available_by_identity = MappingProxyType(
            available_by_identity)
        self._conventional_yolo = MappingProxyType(conventional_yolo)

    def _available_for_identity(self, identity, directory_files):
        available = []
        directories = self._directories_by_identity[identity]
        directory_names = tuple(
            directory_files.get(_directory_identity(directory), ())
            for directory in directories
        )
        for stem_index, stem in enumerate(self._candidates[identity]):
            for extension in ANNOTATION_EXTENSIONS:
                filename = stem + extension
                for directory_index, directory in enumerate(directories):
                    names = directory_names[directory_index]
                    if filename in names:
                        available.append((
                            stem_index, extension, directory_index,
                            os.path.join(directory, filename)))
        return tuple(available)

    def _identity(self, image_path):
        return normalized_image_identity(image_path)

    def contains(self, path):
        directory = os.path.dirname(os.fspath(path))
        names = self._directory_files.get(_directory_identity(directory))
        return names is not None and os.path.basename(os.fspath(path)) in names

    def annotation_stem_candidates(self, image_path):
        identity = self._identity(image_path)
        candidates = self._candidates.get(identity)
        if candidates is not None:
            return candidates
        # Compatibility for a target outside the indexed image list.
        from libs.formats.annotation_paths import annotation_stem_candidates
        return tuple(annotation_stem_candidates(image_path, self.image_paths))

    def image_specific_stem(self, image_path):
        candidates = self.annotation_stem_candidates(image_path)
        if not candidates:
            raise ValueError(
                'Could not derive a unique annotation stem for %s' % image_path)
        return candidates[0]

    def output_stem(self, image_path, extensions=ANNOTATION_EXTENSIONS):
        candidates = self.annotation_stem_candidates(image_path)
        specific = candidates[:-1]
        if candidates and candidates[-1].casefold() != \
                legacy_annotation_stem(image_path).casefold():
            specific = candidates
        if self.save_dir:
            for stem in specific:
                for extension in extensions:
                    extension = (extension if extension.startswith('.')
                                 else '.' + extension)
                    if self.contains(os.path.join(
                            self.save_dir, stem + extension)):
                        return stem
        if self._collisions.get(self._identity(image_path), False):
            if not specific:
                raise ValueError(
                    'Could not derive a unique annotation stem for %s'
                    % image_path)
            return specific[0]
        return legacy_annotation_stem(image_path)

    def output_base(self, image_path):
        if not self.save_dir:
            raise ValueError('An annotation save directory is required')
        return os.path.join(self.save_dir, self.output_stem(image_path))

    def path_candidates(self, image_path, extension):
        if not extension.startswith('.'):
            extension = '.' + extension
        identity = self._identity(image_path)
        paths = []
        directories = self._directories_by_identity.get(identity)
        if directories is None:
            directories = _unique_directories(image_path, self.save_dir)
        for stem in self.annotation_stem_candidates(image_path):
            for directory in directories:
                paths.append(os.path.join(directory, stem + extension))
        return tuple(paths)

    def find_existing(self, image_path, extensions=ANNOTATION_EXTENSIONS):
        identity = self._identity(image_path)
        available = self._available_by_identity.get(identity)
        normalized_extensions = tuple(
            extension if extension.startswith('.') else '.' + extension
            for extension in extensions
        )
        if (available is not None
                and set(normalized_extensions) <= set(ANNOTATION_EXTENSIONS)):
            extension_order = {
                extension: index
                for index, extension in enumerate(normalized_extensions)
            }
            matches = [
                (stem_index, extension_order[extension], directory_index,
                 path)
                for stem_index, extension, directory_index, path in available
                if extension in extension_order
            ]
            return min(matches)[-1] if matches else None

        directories = _unique_directories(image_path, self.save_dir)
        for stem in self.annotation_stem_candidates(image_path):
            for extension in normalized_extensions:
                filename = stem + extension
                for directory in directories:
                    if self.contains(os.path.join(directory, filename)):
                        return os.path.join(directory, filename)
        return None

    def conventional_yolo_path(self, image_path):
        identity = self._identity(image_path)
        if identity in self._conventional_yolo:
            return self._conventional_yolo[identity]
        image_dir = os.path.dirname(os.fspath(image_path))
        path = os.path.join(
            os.path.dirname(image_dir), 'labels',
            legacy_annotation_stem(image_path) + '.txt')
        return path if self.contains(path) else None

    def named_file(self, image_path, filename):
        identity = self._identity(image_path)
        directories = self._directories_by_identity.get(identity)
        if directories is None:
            directories = _unique_directories(image_path, self.save_dir)
        for directory in directories:
            names = self._directory_files.get(
                _directory_identity(directory), ())
            if filename in names:
                path = os.path.join(directory, filename)
                return path
        return None

    def with_file(self, path, present=True, image_path=None):
        """Return an index sharing collision data with one filename changed."""
        path = os.path.abspath(os.fspath(path))
        identity = _directory_identity(os.path.dirname(path))
        directory_files = dict(self._directory_files)
        names = set(directory_files.get(identity, ()))
        if present:
            names.add(os.path.basename(path))
        else:
            names.discard(os.path.basename(path))
        directory_files[identity] = frozenset(names)

        clone = object.__new__(AnnotationResolver)
        clone.image_paths = self.image_paths
        clone.save_dir = self.save_dir
        clone._by_identity = self._by_identity
        clone._candidates = self._candidates
        clone._collisions = self._collisions
        clone._directory_files = MappingProxyType(directory_files)
        clone._directories_by_identity = self._directories_by_identity

        if image_path is not None:
            affected = {self._identity(image_path)}
        else:
            stem = os.path.splitext(os.path.basename(path))[0]
            affected = {
                image_identity
                for image_identity, stems in self._candidates.items()
                if stem in stems
            }
        available = dict(self._available_by_identity)
        conventional_yolo = dict(self._conventional_yolo)
        for image_identity in affected:
            if image_identity not in self._candidates:
                continue
            available[image_identity] = clone._available_for_identity(
                image_identity, directory_files)
            source_path = self._by_identity[image_identity]
            image_dir = os.path.dirname(source_path)
            labels_dir = os.path.join(os.path.dirname(image_dir), 'labels')
            yolo_path = os.path.join(
                labels_dir, legacy_annotation_stem(source_path) + '.txt')
            names = directory_files.get(_directory_identity(labels_dir), ())
            conventional_yolo[image_identity] = (
                yolo_path if os.path.basename(yolo_path) in names else None)
        clone._available_by_identity = MappingProxyType(available)
        clone._conventional_yolo = MappingProxyType(conventional_yolo)
        return clone


@dataclass(frozen=True)
class DatasetSnapshot:
    """A generation-scoped, immutable view of the active dataset."""

    generation: int
    root_dir: object
    save_dir: object
    image_paths: tuple
    path_to_index: object
    resolver: AnnotationResolver
    created_at: float

    @classmethod
    def from_images(cls, image_paths, root_dir=None, save_dir=None,
                    generation=0, sort=False):
        images = [os.path.abspath(os.fspath(path)) for path in image_paths]
        if sort:
            natural_sort(images, key=lambda value: value.lower())
        paths = tuple(images)
        return cls(
            generation=generation,
            root_dir=(os.path.abspath(os.fspath(root_dir))
                      if root_dir else None),
            save_dir=(os.path.abspath(os.fspath(save_dir))
                      if save_dir else None),
            image_paths=paths,
            path_to_index=MappingProxyType({
                path: index for index, path in enumerate(paths)
            }),
            resolver=AnnotationResolver(paths, save_dir),
            created_at=time.monotonic(),
        )

    @classmethod
    def scan(cls, root_dir, save_dir=None, generation=0,
             cancelled=None, progress=None, extensions=None):
        if extensions is None:
            from PyQt6.QtGui import QImageReader
            extensions = tuple(
                '.' + bytes(fmt).decode('ascii').lower()
                for fmt in QImageReader.supportedImageFormats())
        extensions = tuple(extension.lower() for extension in extensions)
        images = []
        visited = 0
        last_progress = time.monotonic()
        for current_root, _dirs, files in os.walk(root_dir):
            if cancelled is not None and cancelled():
                return None
            for filename in files:
                visited += 1
                if filename.lower().endswith(extensions):
                    images.append(os.path.abspath(os.path.join(
                        current_root, filename)))
                now = time.monotonic()
                if progress is not None and (
                        visited % 250 == 0
                        or now - last_progress >= 0.20):
                    progress(visited, len(images))
                    last_progress = now
        if progress is not None:
            progress(visited, len(images))
        return cls.from_images(
            images, root_dir=root_dir, save_dir=save_dir,
            generation=generation, sort=True)

    def without(self, image_path):
        identity = normalized_image_identity(image_path)
        remaining = [
            path for path in self.image_paths
            if normalized_image_identity(path) != identity
        ]
        return DatasetSnapshot.from_images(
            remaining, root_dir=self.root_dir, save_dir=self.save_dir,
            generation=self.generation + 1, sort=False)

    def with_save_dir(self, save_dir):
        return DatasetSnapshot.from_images(
            self.image_paths, root_dir=self.root_dir, save_dir=save_dir,
            generation=self.generation + 1, sort=False)

    def with_generation(self, generation):
        return replace(self, generation=generation)

    def with_annotation_file(self, path, present=True, image_path=None):
        return replace(
            self, resolver=self.resolver.with_file(
                path, present=present, image_path=image_path))
