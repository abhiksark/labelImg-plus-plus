# libs/formats/yolo_seg_io.py
"""YOLO segmentation format reader/writer."""

import os

from libs.utils.constants import DEFAULT_ENCODING

TXT_EXT = '.txt'


class YOLOSegWriter:
    """Writes annotations in YOLO segmentation format (class x1 y1 x2 y2 ... xn yn)."""

    def __init__(self, folder_name, filename, img_size, local_img_path=None):
        self.folder_name = folder_name
        self.filename = filename
        self.img_size = img_size  # [height, width, depth]
        self.local_img_path = local_img_path
        self.verified = False
        self._entries = []

    def add_polygon(self, points, name, difficult):
        """Add polygon annotation. points is list of (x, y) tuples."""
        self._entries.append({
            'name': name,
            'points': points,
            'difficult': difficult,
        })

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        """Add bounding box as 4-point polygon."""
        points = [(x_min, y_min), (x_max, y_min),
                  (x_max, y_max), (x_min, y_max)]
        self.add_polygon(points, name, difficult)

    def save(self, target_file=None, class_list=None):
        """Save annotations to YOLO-seg format text file."""
        if class_list is None:
            class_list = []

        out_path = target_file or (self.filename + TXT_EXT)
        classes_path = os.path.join(
            os.path.dirname(os.path.abspath(out_path)), 'classes.txt')

        h, w = self.img_size[0], self.img_size[1]

        with open(out_path, 'w', encoding=DEFAULT_ENCODING) as f:
            for entry in self._entries:
                name = entry['name']
                if name not in class_list:
                    class_list.append(name)
                class_idx = class_list.index(name)

                coords = []
                for x, y in entry['points']:
                    coords.append('%.6f' % (x / w))
                    coords.append('%.6f' % (y / h))

                f.write('%d %s\n' % (class_idx, ' '.join(coords)))

        with open(classes_path, 'w', encoding=DEFAULT_ENCODING) as f:
            for c in class_list:
                f.write(c + '\n')


class YOLOSegReader:
    """Reads annotations from YOLO segmentation format."""

    def __init__(self, file_path, image, class_list_path=None):
        self.shapes = []
        self.file_path = file_path
        self.verified = False

        if class_list_path is None:
            dir_path = os.path.dirname(os.path.realpath(self.file_path))
            self.class_list_path = os.path.join(dir_path, 'classes.txt')
        else:
            self.class_list_path = class_list_path

        with open(self.class_list_path, 'r') as f:
            self.classes = f.read().strip('\n').split('\n')

        self.img_size = [image.height(), image.width(),
                         1 if image.isGrayscale() else 3]
        self._parse()

    def get_shapes(self):
        """Return list of parsed shapes."""
        return self.shapes

    def _parse(self):
        """Parse YOLO-seg annotation file into shape tuples."""
        h, w = self.img_size[0], self.img_size[1]

        with open(self.file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 7:  # class + min 3 points (6 coords)
                    continue

                class_idx = int(parts[0])
                if class_idx < 0 or class_idx >= len(self.classes):
                    continue

                label = self.classes[class_idx]
                coords = parts[1:]
                if len(coords) % 2 != 0:
                    continue

                points = []
                for i in range(0, len(coords), 2):
                    x = round(float(coords[i]) * w)
                    y = round(float(coords[i + 1]) * h)
                    points.append((x, y))

                # Detect axis-aligned rectangles
                if len(points) == 4:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    if len(set(xs)) == 2 and len(set(ys)) == 2:
                        shape_type = 'rectangle'
                    else:
                        shape_type = 'polygon'
                else:
                    shape_type = 'polygon'

                self.shapes.append(
                    (label, points, None, None, False, shape_type))
