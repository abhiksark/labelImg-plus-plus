#!/usr/bin/env python
# -*- coding: utf8 -*-
import codecs
import os

from libs.constants import DEFAULT_ENCODING

TXT_EXT = '.txt'
ENCODE_METHOD = DEFAULT_ENCODING

class YOLOWriter:

    def __init__(self, folder_name, filename, img_size, database_src='Unknown', local_img_path=None):
        self.folder_name = folder_name
        self.filename = filename
        self.database_src = database_src
        self.img_size = img_size
        self.box_list = []
        self.local_img_path = local_img_path
        self.verified = False

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        bnd_box = {'xmin': x_min, 'ymin': y_min, 'xmax': x_max, 'ymax': y_max}
        bnd_box['name'] = name
        bnd_box['difficult'] = difficult
        self.box_list.append(bnd_box)

    def bnd_box_to_yolo_line(self, box, class_list=[]):
        x_min = box['xmin']
        x_max = box['xmax']
        y_min = box['ymin']
        y_max = box['ymax']

        x_center = float((x_min + x_max)) / 2 / self.img_size[1]
        y_center = float((y_min + y_max)) / 2 / self.img_size[0]

        w = float((x_max - x_min)) / self.img_size[1]
        h = float((y_max - y_min)) / self.img_size[0]

        # PR387
        box_name = box['name']
        if box_name not in class_list:
            class_list.append(box_name)

        class_index = class_list.index(box_name)

        return class_index, x_center, y_center, w, h

    def save(self, class_list=[], target_file=None):
        if target_file is None:
            out_path = self.filename + TXT_EXT
        else:
            out_path = target_file

        classes_file_path = os.path.join(
            os.path.dirname(os.path.abspath(out_path)), "classes.txt"
        )

        # Write annotation file
        with open(out_path, 'w', encoding=ENCODE_METHOD) as out_file:
            for box in self.box_list:
                class_index, x_center, y_center, w, h = self.bnd_box_to_yolo_line(box, class_list)
                out_file.write("%d %.6f %.6f %.6f %.6f\n" % (class_index, x_center, y_center, w, h))

        # Write classes file
        with open(classes_file_path, 'w', encoding=ENCODE_METHOD) as out_class_file:
            for c in class_list:
                out_class_file.write(c + '\n')



class YoloReader:

    def __init__(self, file_path, image, class_list_path=None):
        # shapes type:
        # [labbel, [(x1,y1), (x2,y2), (x3,y3), (x4,y4)], color, color, difficult]
        self.shapes = []
        self.file_path = file_path

        if class_list_path is None:
            dir_path = os.path.dirname(os.path.realpath(self.file_path))
            self.class_list_path = os.path.join(dir_path, "classes.txt")
        else:
            self.class_list_path = class_list_path

        # Load classes with proper error handling
        self.classes = []
        try:
            with open(self.class_list_path, 'r') as classes_file:
                self.classes = classes_file.read().strip('\n').split('\n')
        except FileNotFoundError:
            raise FileNotFoundError(
                f"classes.txt not found at: {self.class_list_path}\n"
                "YOLO format requires a classes.txt file in the same directory as annotations."
            )
        except IOError as e:
            raise IOError(f"Error reading classes.txt: {e}")

        img_size = [image.height(), image.width(),
                    1 if image.isGrayscale() else 3]

        self.img_size = img_size

        self.verified = False
        self.parse_yolo_format()

    def get_shapes(self):
        return self.shapes

    def add_shape(self, label, x_min, y_min, x_max, y_max, difficult):

        points = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
        self.shapes.append((label, points, None, None, difficult))

    def yolo_line_to_shape(self, class_index, x_center, y_center, w, h):
        label = self.classes[int(class_index)]

        x_min = max(float(x_center) - float(w) / 2, 0)
        x_max = min(float(x_center) + float(w) / 2, 1)
        y_min = max(float(y_center) - float(h) / 2, 0)
        y_max = min(float(y_center) + float(h) / 2, 1)

        x_min = round(self.img_size[1] * x_min)
        x_max = round(self.img_size[1] * x_max)
        y_min = round(self.img_size[0] * y_min)
        y_max = round(self.img_size[0] * y_max)

        return label, x_min, y_min, x_max, y_max

    def parse_yolo_format(self):
        with open(self.file_path, 'r') as bnd_box_file:
            for line_num, bndBox in enumerate(bnd_box_file, 1):
                line = bndBox.strip()
                if not line:
                    continue
                parts = line.split(' ')
                if len(parts) != 5:
                    raise ValueError(
                        f"Invalid YOLO format at line {line_num}: expected 5 values, got {len(parts)}"
                    )
                class_index, x_center, y_center, w, h = parts

                # Validate class index
                idx = int(class_index)
                if idx < 0 or idx >= len(self.classes):
                    raise IndexError(
                        f"Class index {idx} at line {line_num} is out of range. "
                        f"classes.txt has {len(self.classes)} classes (0-{len(self.classes)-1})."
                    )

                label, x_min, y_min, x_max, y_max = self.yolo_line_to_shape(class_index, x_center, y_center, w, h)

                # Caveat: difficult flag is discarded when saved as yolo format.
                self.add_shape(label, x_min, y_min, x_max, y_max, False)
