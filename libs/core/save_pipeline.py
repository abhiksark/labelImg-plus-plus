"""Immutable save requests and durable atomic annotation writes."""

from dataclasses import dataclass
import os
import shutil
import tempfile

from libs.formats.labelFile import LabelFile, LabelFileFormat


@dataclass(frozen=True)
class SaveRequest:
    image_path: str
    annotation_path: str
    label_file_format: object
    shapes: tuple
    class_list: tuple
    verified: bool
    revision: int


def extension_for_format(label_file_format):
    if label_file_format in (
            LabelFileFormat.PASCAL_VOC,):
        return '.xml'
    if label_file_format in (
            LabelFileFormat.YOLO, LabelFileFormat.YOLO_SEG):
        return '.txt'
    return '.json'


def target_path(annotation_base, label_file_format):
    extension = extension_for_format(label_file_format)
    return (annotation_base if annotation_base.lower().endswith(extension)
            else annotation_base + extension)


def write_save_request(request, cancelled=None, begin_commit=None):
    """Write one request beside its target and atomically publish it."""
    target = os.path.abspath(request.annotation_path)
    target_dir = os.path.dirname(target)
    os.makedirs(target_dir, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix='.' + os.path.basename(target) + '.', suffix='.tmp',
        dir=target_dir)
    os.close(descriptor)
    try:
        if request.label_file_format in (
                LabelFileFormat.CREATE_ML, LabelFileFormat.COCO):
            if os.path.isfile(target):
                shutil.copyfile(target, temporary)
            else:
                os.unlink(temporary)
        if cancelled is not None and cancelled():
            return None

        label_file = LabelFile()
        label_file.verified = request.verified
        shapes = [dict(shape) for shape in request.shapes]
        class_list = list(request.class_list)
        if request.label_file_format == LabelFileFormat.PASCAL_VOC:
            label_file.save_pascal_voc_format(
                temporary, shapes, request.image_path, None)
        elif request.label_file_format == LabelFileFormat.YOLO:
            label_file.save_yolo_format(
                temporary, shapes, request.image_path, None, class_list)
        elif request.label_file_format == LabelFileFormat.CREATE_ML:
            label_file.save_create_ml_format(
                temporary, shapes, request.image_path, None, class_list)
        elif request.label_file_format == LabelFileFormat.COCO:
            label_file.save_coco_format(
                temporary, shapes, request.image_path, None, class_list)
        elif request.label_file_format == LabelFileFormat.YOLO_SEG:
            label_file.save_yolo_seg_format(
                temporary, shapes, request.image_path, None, class_list)
        else:
            raise ValueError('unsupported annotation format: %r'
                             % request.label_file_format)

        if cancelled is not None and cancelled():
            return None
        # Windows requires a writable descriptor for fsync even though no
        # additional bytes are written here.
        with open(temporary, 'rb+') as output:
            os.fsync(output.fileno())
        if begin_commit is not None:
            begin_commit()
        os.replace(temporary, target)
        try:
            directory_fd = os.open(target_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # Some platforms/filesystems do not permit syncing directories.
            pass
        return target
    finally:
        try:
            if os.path.exists(temporary):
                os.unlink(temporary)
        except OSError:
            pass
