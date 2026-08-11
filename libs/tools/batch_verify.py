"""Two-phase, cancellation-safe PASCAL VOC batch verification."""

import io
import os
import tempfile
import time
import xml.etree.ElementTree as ET

from libs.formats.annotation_paths import find_existing_annotation


def batch_verify_atomic(image_paths, save_dir, verify, handle,
                        resolver=None):
    """Prepare every replacement, then enter a non-cancellable commit phase."""
    image_paths = tuple(image_paths)
    replacements = []
    failures = []
    last_progress = time.monotonic()
    total = len(image_paths)
    for index, image_path in enumerate(image_paths, 1):
        handle.check_cancelled()
        annotation_path = find_existing_annotation(
            image_path, save_dir=save_dir, image_list=image_paths,
            extensions=('.xml', '.txt', '.json'), resolver=resolver)
        if annotation_path is None and resolver is not None:
            annotation_path = resolver.named_file(
                image_path, 'annotations.json')
        if annotation_path:
            if not annotation_path.lower().endswith('.xml'):
                failures.append(
                    (image_path, 'not a PASCAL VOC annotation'))
            else:
                try:
                    tree = ET.parse(annotation_path)
                    root = tree.getroot()
                    if verify:
                        root.set('verified', 'yes')
                    else:
                        root.attrib.pop('verified', None)
                    output = io.BytesIO()
                    tree.write(output)
                    replacements.append((
                        image_path, annotation_path, output.getvalue()))
                except (ET.ParseError, OSError) as exc:
                    failures.append((image_path, str(exc)))
        now = time.monotonic()
        if now - last_progress >= 0.20 or index == total:
            handle.report_progress((index, total))
            last_progress = now

    handle.begin_non_cancellable()
    committed = 0
    for image_path, annotation_path, content in replacements:
        directory = os.path.dirname(os.path.abspath(annotation_path))
        descriptor, temporary = tempfile.mkstemp(
            prefix='.' + os.path.basename(annotation_path) + '.',
            suffix='.tmp', dir=directory)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, annotation_path)
            committed += 1
        except OSError as exc:
            failures.append((image_path, str(exc)))
        finally:
            try:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass
    return committed, failures
