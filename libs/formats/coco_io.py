# libs/formats/coco_io.py
"""COCO JSON annotation format reader/writer."""

import json
import os

from libs.utils.constants import DEFAULT_ENCODING

JSON_EXT = '.json'


class COCOWriter:
    """Writes annotations in COCO JSON format."""

    def __init__(self, folder_name, filename, img_size, local_img_path=None):
        self.folder_name = folder_name
        self.filename = filename
        self.img_size = img_size  # [height, width, depth]
        self.local_img_path = local_img_path
        self.verified = False
        self._annotations = []
        self._categories = {}  # name -> id

    def _get_category_id(self, name):
        if name not in self._categories:
            self._categories[name] = len(self._categories) + 1
        return self._categories[name]

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult, keypoints=None):
        """Add a bounding box annotation in COCO [x, y, w, h] format.

        Args:
            x_min: Left edge of the bounding box.
            y_min: Top edge of the bounding box.
            x_max: Right edge of the bounding box.
            y_max: Bottom edge of the bounding box.
            name: Class label string.
            difficult: Boolean indicating whether the annotation is difficult.
            keypoints: Optional list of 17 elements, each either None or a
                (x, y, visibility) tuple. Visibility: 0=unlabeled,
                1=labeled but occluded, 2=labeled and visible.
        """
        cat_id = self._get_category_id(name)
        ann = {
            'category_id': cat_id,
            'bbox': [x_min, y_min, x_max - x_min, y_max - y_min],
            'iscrowd': 0,
            'difficult': int(difficult),
        }
        if keypoints is not None:
            flat = []
            num_kp = 0
            for kp in keypoints:
                if kp is not None and kp[2] > 0:
                    flat.extend([kp[0], kp[1], kp[2]])
                    num_kp += 1
                else:
                    flat.extend([0, 0, 0])
            ann['keypoints'] = flat
            ann['num_keypoints'] = num_kp
        self._annotations.append(ann)

    def add_polygon(self, points, name, difficult):
        """Add a polygon annotation.

        Args:
            points: List of (x, y) tuples defining the polygon vertices.
            name: Class label string.
            difficult: Boolean indicating whether the annotation is difficult.
        """
        cat_id = self._get_category_id(name)
        flat = []
        x_min, y_min = float('inf'), float('inf')
        x_max, y_max = float('-inf'), float('-inf')
        for x, y in points:
            flat.extend([x, y])
            x_min = min(x_min, x)
            y_min = min(y_min, y)
            x_max = max(x_max, x)
            y_max = max(y_max, y)

        self._annotations.append({
            'category_id': cat_id,
            'segmentation': [flat],
            'bbox': [round(x_min), round(y_min),
                     round(x_max - x_min), round(y_max - y_min)],
            'iscrowd': 0,
            'difficult': int(difficult),
        })

    def save(self, target_file=None):
        """Serialize annotations to a COCO JSON file.

        Args:
            target_file: Output file path. Defaults to annotations.json
                alongside the source image when not provided.
        """
        out_path = target_file or os.path.join(
            os.path.dirname(self.local_img_path or ''), 'annotations.json')

        image_entry = {
            'id': 1,
            'file_name': self.filename,
            'width': self.img_size[1],
            'height': self.img_size[0],
        }

        annotations = []
        has_keypoints = False
        for i, ann in enumerate(self._annotations, 1):
            entry = {'id': i, 'image_id': 1}
            entry.update(ann)
            annotations.append(entry)
            if 'keypoints' in ann:
                has_keypoints = True

        categories = []
        for name, cid in self._categories.items():
            cat = {'id': cid, 'name': name}
            if name.lower() == 'person' and has_keypoints:
                from libs.core.keypoint_config import COCO_KEYPOINT_NAMES, COCO_SKELETON
                cat['keypoints'] = list(COCO_KEYPOINT_NAMES)
                cat['skeleton'] = [[a + 1, b + 1] for a, b in COCO_SKELETON]
            categories.append(cat)

        coco = {
            'images': [image_entry],
            'annotations': annotations,
            'categories': categories,
        }

        with open(out_path, 'w', encoding=DEFAULT_ENCODING) as f:
            json.dump(coco, f, indent=2)


class COCOReader:
    """Reads annotations from COCO JSON format."""

    def __init__(self, file_path, target_filename=None):
        self.shapes = []
        self.file_path = file_path
        self.verified = False
        self._parse(target_filename)

    def get_shapes(self):
        """Return parsed shapes as a list of tuples.

        Each tuple has the form:
            (label, points, line_color, fill_color, difficult, shape_type,
             keypoints)

        ``keypoints`` is a list of 17 elements, each either None or a
        (x, y, visibility) tuple, or None when no keypoint data is present.
        """
        return self.shapes

    def _parse(self, target_filename):
        with open(self.file_path, 'r', encoding=DEFAULT_ENCODING) as f:
            data = json.load(f)

        cat_map = {c['id']: c['name'] for c in data.get('categories', [])}

        images = data.get('images', [])
        target_image_id = None
        if target_filename:
            for img in images:
                if img['file_name'] == target_filename:
                    target_image_id = img['id']
                    break
        if target_image_id is None and images:
            target_image_id = images[0]['id']

        for ann in data.get('annotations', []):
            if ann.get('image_id') != target_image_id:
                continue

            label = cat_map.get(ann['category_id'], 'unknown')
            difficult = bool(ann.get('difficult', 0))

            # Parse keypoints if present.
            kp_data = None
            if 'keypoints' in ann and ann['keypoints']:
                flat = ann['keypoints']
                kp_data = []
                for i in range(0, len(flat), 3):
                    x, y, v = flat[i], flat[i + 1], flat[i + 2]
                    if v == 0 and x == 0 and y == 0:
                        kp_data.append(None)
                    else:
                        kp_data.append((x, y, int(v)))

            if 'segmentation' in ann and ann['segmentation']:
                seg = ann['segmentation'][0]
                points = [(seg[i], seg[i + 1]) for i in range(0, len(seg), 2)]
                self.shapes.append(
                    (label, points, None, None, difficult, 'polygon', None))
            else:
                bbox = ann['bbox']  # [x, y, w, h]
                x, y, w, h = bbox
                points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                self.shapes.append(
                    (label, points, None, None, difficult, 'rectangle', kp_data))
