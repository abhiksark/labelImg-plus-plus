# scripts/_demo_setup.py
"""Workspace builder for the demo-GIF generator (scripts/make_demo_gif.py).

The generator drives a real, offscreen ``MainWindow`` and grabs frames, so the
only thing it needs from here is a throwaway dataset: an image directory with a
few cat photos (so gallery mode shows several thumbnails), a ``classes.txt``,
and an empty save directory.

Subcommand (handy for debugging):
  workspace <outdir>   build the image dir + classes.txt; print JSON of paths
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The one clean annotation photo bundled with the repo (also the README still).
CAT_PHOTO = os.path.join(REPO_ROOT, 'resources', 'demo', 'demo_image.jpg')
# 'face' doubles as a keypoint template name (libs/core/keypoint_config.py).
CLASSES = ['cat', 'face', 'dog', 'person', 'car']


def build_workspace(outdir):
    """Create the temp image dir, save dir, and classes.txt. Return paths.

    The annotation subject is the bundled cat photo. A few derived variants
    (flip, brighten, darken) give gallery mode several distinct thumbnails while
    keeping every image a clean photo. ``1_cat.jpg`` sorts first, so it is the
    image the app opens and the one the tour annotates.
    """
    from PIL import Image, ImageEnhance

    image_dir = os.path.join(outdir, 'images')
    save_dir = os.path.join(outdir, 'labels')
    os.makedirs(image_dir, exist_ok=True)
    os.makedirs(save_dir, exist_ok=True)

    base = Image.open(CAT_PHOTO).convert('RGB')
    variants = [
        ('1_cat.jpg', base),
        ('2_cat.jpg', base.transpose(Image.FLIP_LEFT_RIGHT)),
        ('3_cat.jpg', ImageEnhance.Brightness(base).enhance(1.25)),
        ('4_cat.jpg', ImageEnhance.Brightness(base).enhance(0.78)),
    ]
    paths = []
    for name, img in variants:
        dst = os.path.join(image_dir, name)
        img.save(dst, quality=90)
        paths.append(dst)

    classes_path = os.path.join(outdir, 'classes.txt')
    with open(classes_path, 'w') as handle:
        handle.write('\n'.join(CLASSES) + '\n')

    return {
        'image_dir': image_dir,
        'classes': classes_path,
        'save_dir': save_dir,
        'first_image': paths[0],
        'num_images': len(paths),
    }


def main(argv):
    if len(argv) >= 3 and argv[1] == 'workspace':
        print(json.dumps(build_workspace(argv[2])))
        return 0
    sys.stderr.write('usage: _demo_setup.py workspace <outdir>\n')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
