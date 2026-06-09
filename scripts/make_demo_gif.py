# scripts/make_demo_gif.py
"""Generate resources/demo/demo.gif - an animated feature tour of labelImg++.

The tour runs the *real* MainWindow offscreen and drives it entirely through
the data model (load_labels, theme toggle, gallery toggle) - no mouse
simulation, no display server. Each scene is captured with QWidget.grab() and
the frames are encoded to an animated GIF with Pillow.

  No Xvfb, no xdotool, no ffmpeg - just PyQt5 + Pillow, headless and
  deterministic. Re-run any time the UI changes:

      make demo-gif
      python3 scripts/make_demo_gif.py --out resources/demo/demo.gif

Story (the "++" differentiators): gallery -> bounding box -> dark theme ->
polygon -> face keypoints -> save.
"""

import argparse
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

# The bundled cat photo is 1200x1602. Shape coordinates below are expressed as
# fractions of this image, so they track the subject if the photo is replaced.
IMG_W, IMG_H = 1200, 1602
WIN_W, WIN_H = 1280, 800

DEFAULT_OUT = os.path.join(REPO_ROOT, 'resources', 'demo', 'demo.gif')
DEFAULT_FPS = 12
DEFAULT_WIDTH = 900


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested in tests/tools/test_make_demo_gif.py)
# --------------------------------------------------------------------------- #
def qpixmap_to_pil(pixmap):
    """Convert a QPixmap to a PIL RGB Image (no display server required)."""
    from PIL import Image
    from PyQt5.QtGui import QImage

    qimg = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    width, height = qimg.width(), qimg.height()
    ptr = qimg.constBits()
    nbytes = qimg.sizeInBytes() if hasattr(qimg, 'sizeInBytes') else qimg.byteCount()
    ptr.setsize(nbytes)
    return Image.frombytes('RGBA', (width, height), bytes(ptr)).convert('RGB')


# Saturated UI marks that occupy too few pixels to win an adaptive-palette slot
# and otherwise get mapped to a nearby muted colour during GIF quantization.
ACCENT_COLORS = [
    (78, 205, 196),    # keypoint eye   (#4ecdc4)
    (255, 107, 107),   # keypoint nose  (#ff6b6b)
    (255, 217, 61),    # keypoint mouth (#ffd93d)
    (0, 255, 0),       # shape vertex highlight
    (255, 255, 255),   # keypoint dot outline
]


def _quantize_preserving_accents(frame):
    """Adaptive-palette an RGB frame, reserving exact slots for ACCENT_COLORS."""
    from PIL import Image

    reserved = len(ACCENT_COLORS)
    base = frame.convert('P', palette=Image.ADAPTIVE, colors=256 - reserved)
    palette = base.getpalette()[:(256 - reserved) * 3]
    for r, g, b in ACCENT_COLORS:
        palette += [r, g, b]
    palette += [0] * (768 - len(palette))

    pal_img = Image.new('P', (1, 1))
    pal_img.putpalette(palette)
    return frame.quantize(palette=pal_img, dither=Image.NONE)


def assemble_gif(frames, out_path, fps=DEFAULT_FPS, width=DEFAULT_WIDTH, loop=0):
    """Encode a list of PIL images into an animated GIF.

    Frames get a per-frame adaptive palette (so the light->dark transition
    keeps its colours) with exact slots reserved for ACCENT_COLORS, so small
    saturated marks - keypoint dots, vertices - survive quantization.
    """
    from PIL import Image

    if not frames:
        raise ValueError("assemble_gif: no frames to write")

    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:  # Pillow < 9.1
        resample = Image.LANCZOS

    duration = max(20, int(round(1000.0 / fps)))

    # Every GIF frame must share one canvas size. Derive it from the first
    # frame and force every frame to match - a safety net against grabs that
    # come back at a different size (e.g. a maximized child window).
    first = frames[0].convert('RGB')
    fw, fh = first.size
    target = (width, max(1, int(round(fh * width / float(fw)))))

    paletted = []
    for frame in frames:
        frame = frame.convert('RGB')
        if frame.size != target:
            frame = frame.resize(target, resample)
        paletted.append(_quantize_preserving_accents(frame))

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    paletted[0].save(
        out_path, save_all=True, append_images=paletted[1:],
        duration=duration, loop=loop, optimize=True, disposal=2)
    return out_path


# --------------------------------------------------------------------------- #
# Shape builders (image-fraction -> labelImg shape tuples)
# --------------------------------------------------------------------------- #
def _rect(fx1, fy1, fx2, fy2):
    """Four-corner rectangle (labelImg stores boxes as 4 points)."""
    x1, y1, x2, y2 = fx1 * IMG_W, fy1 * IMG_H, fx2 * IMG_W, fy2 * IMG_H
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def _poly(fracs):
    return [(fx * IMG_W, fy * IMG_H) for fx, fy in fracs]


# (label, points, line_color, fill_color, difficult, shape_type, keypoints)
def cat_box(progress=1.0):
    """The cat bounding box, optionally grown to ``progress`` (0..1)."""
    fx1, fy1, fx2, fy2 = 0.18, 0.05, 0.83, 0.96
    fx2 = fx1 + (fx2 - fx1) * progress
    fy2 = fy1 + (fy2 - fy1) * progress
    return ('cat', _rect(fx1, fy1, fx2, fy2), None, None, False, 'rectangle', None)


CAT_OUTLINE = [
    (0.39, 0.07), (0.50, 0.10), (0.55, 0.20), (0.58, 0.31), (0.78, 0.45),
    (0.82, 0.78), (0.80, 0.93), (0.50, 0.95), (0.34, 0.93), (0.22, 0.70),
    (0.21, 0.42), (0.24, 0.27), (0.28, 0.10),
]


def cat_polygon():
    return ('cat', _poly(CAT_OUTLINE), None, None, False, 'polygon', None)


# Face keypoints (face template: left_eye, right_eye, nose, left_mouth,
# right_mouth), calibrated against the cat's actual features in demo_image.jpg.
FACE_KEYPOINTS = [
    (0.345, 0.265), (0.460, 0.265), (0.398, 0.325), (0.376, 0.358), (0.430, 0.358),
]


def face_box(n_visible=5):
    """Face rectangle carrying the first ``n_visible`` keypoints."""
    kps = [
        (fx * IMG_W, fy * IMG_H, 2) if i < n_visible else None
        for i, (fx, fy) in enumerate(FACE_KEYPOINTS)
    ]
    return ('face', _rect(0.27, 0.10, 0.53, 0.40), None, None, False, 'rectangle', kps)


# --------------------------------------------------------------------------- #
# Driving the app
# --------------------------------------------------------------------------- #
def _set_shapes(win, tuples):
    """Replace the canvas annotations with ``tuples`` (clears label lists first
    so repeated calls don't duplicate entries), and paint labels on canvas."""
    win.rect_label_list.clear()
    win.poly_label_list.clear()
    win.items_to_shapes.clear()
    win.shapes_to_items.clear()
    win.load_labels(tuples)
    for shape in win.canvas.shapes:
        shape.paint_label = True
    win.paint_canvas()


class Tour:
    """Builds the frame sequence by driving a live, offscreen MainWindow."""

    def __init__(self, app, win, fps):
        self.app = app
        self.win = win
        self.fps = fps
        self.frames = []

    def _pump(self, seconds=0.0):
        """Flush the Qt event loop (and optionally idle) so pending repaints,
        timers and thumbnail workers settle before a grab."""
        deadline = seconds
        elapsed = 0.0
        self.app.processEvents()
        while elapsed < deadline:
            self.app.processEvents()
            time.sleep(0.03)
            elapsed += 0.03

    def hold(self, seconds, widget=None):
        """Capture the current state and hold it for ``seconds``."""
        widget = widget or self.win
        self._pump()
        frame = qpixmap_to_pil(widget.grab())
        n = max(1, int(round(seconds * self.fps)))
        self.frames.extend([frame] * n)

    def step(self, widget=None):
        """Capture exactly one frame of the current state (for transitions)."""
        widget = widget or self.win
        self._pump()
        self.frames.append(qpixmap_to_pil(widget.grab()))

    # -- scenes -------------------------------------------------------------- #
    def scene_intro(self):
        self.win.set_clean()
        self.hold(0.7)

    def scene_gallery(self):
        self.win.toggle_gallery_mode(True)
        gallery = getattr(self.win, 'gallery_window', None)
        if gallery is None:                       # defensive: skip if unavailable
            return
        # toggle_gallery_mode showMaximized()s the window, which under the
        # offscreen platform shrinks it to the tiny virtual screen. Force it
        # back to the tour's window size so every frame shares one canvas.
        self._pump(0.5)                           # let the initial layout settle
        gallery.showNormal()
        gallery.setFixedSize(WIN_W, WIN_H)
        self._pump(0.7)                           # re-flow thumbnails at full size
        self.hold(2.0, widget=gallery)
        self.win.toggle_gallery_mode(False)
        self._pump(0.2)

    def scene_bounding_box(self):
        for k in range(1, 7):                     # grow the box
            _set_shapes(self.win, [cat_box(k / 6.0)])
            self.step()
        self.win.set_dirty()
        self.hold(1.3)

    def scene_dark_theme(self):
        self.win.dark_mode_action.setChecked(True)
        self.win._toggle_dark_mode()
        self.hold(1.5)

    def scene_polygon(self):
        _set_shapes(self.win, [cat_box(), cat_polygon()])
        self.hold(1.4)

    def _scroll_to(self, fx, fy):
        """Scroll so image-fraction (fx, fy) is roughly in view."""
        from PyQt5.QtCore import Qt
        self._pump()
        for orient, frac in ((Qt.Horizontal, fx), (Qt.Vertical, fy)):
            bar = self.win.scroll_bars[orient]
            span = bar.maximum() - bar.minimum()
            bar.setValue(int(bar.minimum() + span * frac))

    def scene_keypoints(self):
        # Zoom into the cat's face so the 5 colour-coded keypoints read clearly.
        # Drop the polygon here so they aren't lost among its vertices; keep the
        # cat box as a continuity anchor.
        self.win.set_fit_window(True)
        self.win.paint_canvas()
        self._pump()
        fit = self.win.zoom_widget.value()
        self.win.set_zoom(int(fit * 2.0))
        _set_shapes(self.win, [cat_box(), face_box(0)])
        self._scroll_to(0.5, 0.12)                # frame the head
        self.hold(0.6)
        for n in range(1, 6):                     # drop one keypoint at a time
            _set_shapes(self.win, [cat_box(), face_box(n)])
            self._scroll_to(0.5, 0.12)
            self.hold(0.34)
        self.hold(1.3)

    def scene_save(self):
        # Zoom back out to the whole cat with every annotation type, then save.
        self.win.set_fit_window(True)
        _set_shapes(self.win, [cat_box(), cat_polygon(), face_box(5)])
        self.win.paint_canvas()
        self._pump()
        self.win.set_clean()
        self.hold(1.8)

    def run(self):
        self.scene_intro()
        self.scene_gallery()
        self.scene_bounding_box()
        self.scene_dark_theme()
        self.scene_polygon()
        self.scene_keypoints()
        self.scene_save()
        return self.frames


def _build_window(workspace):
    """Construct the offscreen app pointed at the demo workspace and load the
    first cat image at a fixed 1280x800 window, fit to view."""
    from labelImgPlusPlus import get_main_app

    argv = ['labelImgpp', workspace['image_dir'],
            workspace['classes'], workspace['save_dir']]
    app, win = get_main_app(argv)
    app.processEvents()                            # flush queued dir import
    win.resize(WIN_W, WIN_H)
    app.processEvents()
    win.load_file(workspace['first_image'])        # guarantee the cat is shown
    win.adjust_scale(initial=True)                 # fit to the resized window
    win.paint_canvas()
    app.processEvents()
    return app, win


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=DEFAULT_OUT)
    parser.add_argument('--fps', type=int, default=DEFAULT_FPS)
    parser.add_argument('--width', type=int, default=DEFAULT_WIDTH)
    parser.add_argument('--keep-workspace', action='store_true',
                        help="don't delete the temp dataset (for debugging)")
    args = parser.parse_args(argv)

    import shutil
    import tempfile
    import _demo_setup

    workspace_root = tempfile.mkdtemp(prefix='labelimg-demo-')
    try:
        workspace = _demo_setup.build_workspace(workspace_root)
        app, win = _build_window(workspace)
        frames = Tour(app, win, args.fps).run()
        assemble_gif(frames, args.out, fps=args.fps, width=args.width)
    finally:
        if not args.keep_workspace:
            shutil.rmtree(workspace_root, ignore_errors=True)

    size_kib = os.path.getsize(args.out) // 1024
    print("Wrote %s (%d frames, %d KiB)" % (args.out, len(frames), size_kib))
    if size_kib > 12000:
        print("WARNING: GIF > ~12MB; lower --fps or --width", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
