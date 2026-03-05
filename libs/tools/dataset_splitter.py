# libs/tools/dataset_splitter.py
"""Dataset splitting tool for train/val/test partitioning."""

import json
import os
import random
import shutil
from collections import defaultdict
from datetime import datetime


def find_annotation_file(img_path, save_dir=None):
    """Find the annotation file matching an image.

    Args:
        img_path: Path to the image file.
        save_dir: Optional directory where annotations are saved.

    Returns:
        Path to the matching annotation file, or None if not found.
    """
    basename = os.path.splitext(os.path.basename(img_path))[0]
    search_dirs = []
    if save_dir:
        search_dirs.append(save_dir)
    search_dirs.append(os.path.dirname(img_path))

    for d in search_dirs:
        for ext in ['.xml', '.txt', '.json']:
            path = os.path.join(d, basename + ext)
            if os.path.isfile(path):
                return path
    return None


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
    rng = random.Random(seed)

    if stratified:
        label_groups = defaultdict(list)
        for img in image_list:
            ann = find_annotation_file(img, save_dir)
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

    images = list(image_list)
    rng.shuffle(images)
    n = len(images)
    n_train = round(n * ratios['train'])
    n_val = round(n * ratios['val'])
    return {
        'train': images[:n_train],
        'val': images[n_train:n_train + n_val],
        'test': images[n_train + n_val:],
    }


def execute_split(splits, output_dir, save_dir=None, copy=True):
    """Copy or symlink files into train/val/test directories.

    Args:
        splits: Dict from split_dataset().
        output_dir: Base output directory.
        save_dir: Annotation save directory.
        copy: If True, copy files. If False, create symlinks.

    Returns:
        Path to the generated manifest file.
    """
    manifest = {
        'created': datetime.now().isoformat(),
        'files': {},
    }

    for split_name, images in splits.items():
        split_dir = os.path.join(output_dir, split_name)
        os.makedirs(split_dir, exist_ok=True)
        manifest['files'][split_name] = []

        for img_path in images:
            basename = os.path.basename(img_path)
            dest = os.path.join(split_dir, basename)

            if copy:
                shutil.copy2(img_path, dest)
            else:
                os.symlink(os.path.abspath(img_path), dest)

            manifest['files'][split_name].append(basename)

            ann = find_annotation_file(img_path, save_dir)
            if ann:
                ann_dest = os.path.join(split_dir, os.path.basename(ann))
                if copy:
                    shutil.copy2(ann, ann_dest)
                else:
                    os.symlink(os.path.abspath(ann), ann_dest)

    manifest_path = os.path.join(output_dir, 'split_manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    return manifest_path
