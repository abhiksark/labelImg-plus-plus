# libs/tools/dataset_splitter.py
"""Dataset splitting tool for train/val/test partitioning."""

import hashlib
import json
import os
import random
import shutil
from collections import defaultdict
from datetime import datetime

from libs.formats.annotation_paths import find_existing_annotation


def find_annotation_file(img_path, save_dir=None, image_list=None):
    """Find the annotation file matching an image.

    Args:
        img_path: Path to the image file.
        save_dir: Optional directory where annotations are saved.
        image_list: Optional complete image list used to resolve basename
            collisions.

    Returns:
        Path to the matching annotation file, or None if not found.
    """
    return find_existing_annotation(
        img_path,
        save_dir=save_dir,
        image_list=image_list,
        extensions=('.xml', '.txt', '.json'),
    )


def get_labels_from_xml(xml_path):
    """Extract label names from a PascalVOC XML file.

    Args:
        xml_path: Path to a PascalVOC XML annotation file.

    Returns:
        List of label name strings found in the annotation.
    """
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(xml_path)
        return [obj.find('name').text for obj in tree.findall('object')]
    except Exception:
        return []


def split_dataset(image_list, ratios, seed=42, stratified=False,
                  save_dir=None):
    """Split image list into train/val/test sets.

    Args:
        image_list: List of image file paths.
        ratios: Dict with keys 'train', 'val', 'test' summing to 1.0.
        seed: Random seed for reproducibility.
        stratified: If True, balance class distribution across splits.
        save_dir: Directory where annotations are saved (for stratification).

    Returns:
        Dict with keys 'train', 'val', 'test', each a list of image paths.
    """
    total = sum(ratios.get(k, 0) for k in ('train', 'val', 'test'))
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"Split ratios must sum to 1.0 (got {total:.3f})")

    rng = random.Random(seed)
    images = list(image_list)

    if stratified:
        label_groups = defaultdict(list)
        for img in images:
            ann = find_annotation_file(img, save_dir, images)
            if ann and ann.endswith('.xml'):
                labels = get_labels_from_xml(ann)
                primary = labels[0] if labels else '_unlabeled'
            else:
                primary = '_unlabeled'
            label_groups[primary].append(img)

        result = {'train': [], 'val': [], 'test': []}
        for label, images in label_groups.items():
            rng.shuffle(images)
            n = len(images)
            n_train = max(1, round(n * ratios['train']))
            n_val = max(0, round(n * ratios['val']))
            result['train'].extend(images[:n_train])
            result['val'].extend(images[n_train:n_train + n_val])
            result['test'].extend(images[n_train + n_val:])
        return result

    rng.shuffle(images)
    n = len(images)
    n_train = round(n * ratios['train'])
    n_val = round(n * ratios['val'])
    return {
        'train': images[:n_train],
        'val': images[n_train:n_train + n_val],
        'test': images[n_train + n_val:],
    }


def _find_classes_file(save_dir, splits):
    """Locate a classes.txt for YOLO splits (save_dir first, then image dirs)."""
    candidates = []
    if save_dir:
        candidates.append(os.path.join(save_dir, 'classes.txt'))
    for images in splits.values():
        for img in images:
            candidates.append(os.path.join(os.path.dirname(img), 'classes.txt'))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _place_file(src, dest, copy):
    """Copy or symlink src->dest. Caller guarantees dest does not yet exist."""
    if copy:
        shutil.copy2(src, dest)
    else:
        os.symlink(os.path.abspath(src), dest)


def _source_key(path):
    """Return a stable key for repeated references to the same source path."""
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def _relative_identity(path, group_paths):
    """Return a relocation-friendly identity within a colliding path group."""
    absolute_path = os.path.abspath(os.path.normpath(path))
    try:
        common_root = os.path.commonpath([
            os.path.dirname(os.path.abspath(os.path.normpath(group_path)))
            for group_path in group_paths
        ])
        identity = os.path.relpath(absolute_path, common_root)
    except (OSError, ValueError):
        # ``commonpath`` raises for paths on different Windows drives. The
        # absolute path is still deterministic for reruns in that case.
        identity = absolute_path

    if os.sep != '/':
        identity = identity.replace(os.sep, '/')
    if os.altsep:
        identity = identity.replace(os.altsep, '/')
    return identity


def _build_output_names(images):
    """Choose deterministic, flat output names without basename collisions.

    A unique stem retains its legacy basename. When distinct source images
    share a stem, every image receives a suffix derived from its path relative
    to the collision group's common root. The mapping depends only on the
    sources, not on iteration order or the current output directory, so reruns
    resolve to the same destinations.
    """
    groups = defaultdict(dict)
    for img_path in images:
        basename = os.path.basename(img_path)
        stem, extension = os.path.splitext(basename)
        groups[stem.casefold()][_source_key(img_path)] = {
            'path': img_path,
            'stem': stem,
            'extension': extension,
            'basename': basename,
        }

    output_names = {}
    used_stems = set()

    # Reserve all legacy stems first so neither an image nor its paired
    # annotation can collide with an otherwise non-conflicting source.
    for stem_key in sorted(groups):
        group = groups[stem_key]
        if len(group) != 1:
            continue
        source_key, source = next(iter(group.items()))
        output_names[source_key] = source['basename']
        used_stems.add(source['stem'].casefold())

    for stem_key in sorted(groups):
        group = groups[stem_key]
        if len(group) <= 1:
            continue

        group_paths = [source['path'] for source in group.values()]
        for source_key in sorted(group):
            source = group[source_key]
            identity = _relative_identity(source['path'], group_paths)
            digest = hashlib.sha256(os.fsencode(identity)).hexdigest()

            output_name = None
            for digest_length in (12, 16, 24, 32, 64):
                candidate_stem = '{}__{}'.format(
                    source['stem'], digest[:digest_length])
                if candidate_stem.casefold() not in used_stems:
                    output_name = candidate_stem + source['extension']
                    break

            # Account even for an adversarial source whose literal stem
            # matches every hash candidate. Sorting above keeps this fallback
            # deterministic.
            if output_name is None:
                counter = 1
                while True:
                    candidate_stem = '{}__{}-{}'.format(
                        source['stem'], digest, counter)
                    if candidate_stem.casefold() not in used_stems:
                        output_name = candidate_stem + source['extension']
                        break
                    counter += 1

            output_names[source_key] = output_name
            used_stems.add(os.path.splitext(output_name)[0].casefold())

    return output_names


def execute_split(splits, output_dir, save_dir=None, copy=True):
    """Copy or symlink files into train/val/test directories.

    Existing destination files are never overwritten (recorded under
    ``skipped``), per-file failures are collected (under ``errors``) instead of
    aborting the whole split, and a YOLO ``classes.txt`` is copied into each
    split so the integer labels remain decodable.

    Args:
        splits: Dict from split_dataset().
        output_dir: Base output directory.
        save_dir: Annotation save directory.
        copy: If True, copy files. If False, create symlinks.

    Returns:
        Path to the generated manifest file (always written, even on failures).
    """
    manifest = {
        'created': datetime.now().isoformat(),
        'files': {},
        'skipped': [],
        'errors': [],
    }
    classes_src = _find_classes_file(save_dir, splits)
    all_images = [
        image_path
        for images in splits.values()
        for image_path in images
    ]

    try:
        for split_name, images in splits.items():
            split_dir = os.path.join(output_dir, split_name)
            os.makedirs(split_dir, exist_ok=True)
            manifest['files'][split_name] = []
            wrote_yolo = False
            output_names = _build_output_names(images)

            for img_path in images:
                output_name = output_names[_source_key(img_path)]
                dest = os.path.join(split_dir, output_name)
                if os.path.lexists(dest):
                    manifest['skipped'].append(dest)  # never clobber
                    continue
                try:
                    _place_file(img_path, dest, copy)
                except OSError as e:
                    manifest['errors'].append(
                        {'file': img_path, 'error': str(e)})
                    continue

                manifest['files'][split_name].append(output_name)

                ann = find_annotation_file(
                    img_path, save_dir, all_images)
                if ann:
                    output_stem = os.path.splitext(output_name)[0]
                    annotation_extension = os.path.splitext(ann)[1]
                    ann_dest = os.path.join(
                        split_dir, output_stem + annotation_extension)
                    if not os.path.lexists(ann_dest):
                        try:
                            _place_file(ann, ann_dest, copy)
                        except OSError as e:
                            manifest['errors'].append(
                                {'file': ann, 'error': str(e)})
                    else:
                        manifest['skipped'].append(ann_dest)
                    if ann.endswith('.txt'):
                        wrote_yolo = True

            # YOLO labels are useless without their class map.
            if wrote_yolo and classes_src:
                classes_dest = os.path.join(split_dir, 'classes.txt')
                if not os.path.lexists(classes_dest):
                    try:
                        shutil.copy2(classes_src, classes_dest)
                    except OSError as e:
                        manifest['errors'].append(
                            {'file': classes_src, 'error': str(e)})
    finally:
        manifest_path = os.path.join(output_dir, 'split_manifest.json')
        os.makedirs(output_dir, exist_ok=True)
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    return manifest_path
