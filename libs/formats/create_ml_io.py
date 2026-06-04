#!/usr/bin/env python
# -*- coding: utf8 -*-
import json
from pathlib import Path

from libs.utils.constants import DEFAULT_ENCODING
import os

JSON_EXT = '.json'
ENCODE_METHOD = DEFAULT_ENCODING


class CreateMLWriter:
    def __init__(self, folder_name, filename, img_size, shapes, output_file, database_src='Unknown', local_img_path=None):
        self.folder_name = folder_name
        self.filename = filename
        self.database_src = database_src
        self.img_size = img_size
        self.box_list = []
        self.local_img_path = local_img_path
        self.verified = False
        self.shapes = shapes
        self.output_file = output_file

    def write(self):
        if os.path.isfile(self.output_file):
            with open(self.output_file, "r") as file:
                input_data = file.read()
                output_dict = json.loads(input_data)
        else:
            output_dict = []

        output_image_dict = {
            "image": self.filename,
            "verified": self.verified,
            "annotations": []
        }

        for shape in self.shapes:
            points = shape["points"]

            x1 = points[0][0]
            y1 = points[0][1]
            x2 = points[1][0]
            y2 = points[2][1]

            height, width, x, y = self.calculate_coordinates(x1, x2, y1, y2)

            shape_dict = {
                "label": shape["label"],
                "coordinates": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height
                }
            }
            output_image_dict["annotations"].append(shape_dict)

        # check if image already in output
        exists = False
        for i in range(0, len(output_dict)):
            if output_dict[i]["image"] == output_image_dict["image"]:
                exists = True
                output_dict[i] = output_image_dict
                break

        if not exists:
            output_dict.append(output_image_dict)

        Path(self.output_file).write_text(json.dumps(output_dict), ENCODE_METHOD)

    def calculate_coordinates(self, x1, x2, y1, y2):
        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)
        width = x_max - x_min
        height = y_max - y_min
        # x and y from center of rect
        x = x_min + width / 2
        y = y_min + height / 2
        return height, width, x, y


class CreateMLReader:
    def __init__(self, json_path, file_path):
        self.json_path = json_path
        self.shapes = []
        self.verified = False
        self.filename = os.path.basename(file_path)
        # Let parse failures propagate so callers can surface them, instead
        # of silently swallowing a malformed file into an empty shape list.
        self.parse_json()

    def parse_json(self):
        with open(self.json_path, "r") as file:
            input_data = file.read()

        output_list = json.loads(input_data)

        # A CreateML file is a JSON array of image objects; anything else is
        # malformed. Fail with a clear error instead of an opaque TypeError.
        if not isinstance(output_list, list):
            raise ValueError("CreateML annotation file must be a JSON array")

        if output_list and isinstance(output_list[0], dict):
            self.verified = output_list[0].get("verified", False)

        for image in output_list:
            if not isinstance(image, dict):
                continue
            if image.get("image") == self.filename:
                for shape in image.get("annotations", []):
                    label = shape.get("label")
                    coords = shape.get("coordinates")
                    if label is None or not isinstance(coords, dict):
                        continue
                    if not all(k in coords
                               for k in ("x", "y", "width", "height")):
                        continue
                    self.add_shape(label, coords)

    def add_shape(self, label, bnd_box):
        x_min = bnd_box["x"] - (bnd_box["width"] / 2)
        y_min = bnd_box["y"] - (bnd_box["height"] / 2)

        x_max = bnd_box["x"] + (bnd_box["width"] / 2)
        y_max = bnd_box["y"] + (bnd_box["height"] / 2)

        points = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
        self.shapes.append((label, points, None, None, True))

    def get_shapes(self):
        return self.shapes
