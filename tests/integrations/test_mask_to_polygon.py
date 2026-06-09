# tests/integrations/test_mask_to_polygon.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from libs.integrations.mask_to_polygon import mask_to_polygon


def _square(size=200, lo=40, hi=160):
    m = np.zeros((size, size), dtype=bool)
    m[lo:hi, lo:hi] = True
    return m


def test_filled_square_yields_a_few_points():
    pts = mask_to_polygon(_square())
    assert pts is not None
    assert 4 <= len(pts) <= 8           # a quad, perhaps a couple extra
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) <= 41 and max(xs) >= 159   # 1-px tolerance: contour starts inside the fill
    assert min(ys) <= 41 and max(ys) >= 159


def test_empty_mask_returns_none():
    assert mask_to_polygon(np.zeros((100, 100), dtype=bool)) is None


def test_speck_below_area_floor_returns_none():
    m = np.zeros((1000, 1000), dtype=bool)
    m[0:3, 0:3] = True                  # 9px << 0.05% of 1e6
    assert mask_to_polygon(m) is None


def test_two_blobs_keeps_only_the_largest():
    m = np.zeros((200, 200), dtype=bool)
    m[10:30, 10:30] = True              # small
    m[80:180, 80:180] = True            # large
    pts = mask_to_polygon(m)
    xs = [p[0] for p in pts]
    assert min(xs) >= 70                # only the large blob survives


def test_point_cap_is_honored():
    # a noisy disk that would simplify to many points at small epsilon
    yy, xx = np.mgrid[0:300, 0:300]
    m = ((xx - 150) ** 2 + (yy - 150) ** 2) < 120 ** 2
    pts = mask_to_polygon(m, max_points=20)
    assert pts is not None and len(pts) <= 20


def test_tight_cap_forces_epsilon_bump():
    # A disk simplifies to ~9 points at the default epsilon, so a cap of 6
    # must drive the epsilon-bump loop at least once.
    yy, xx = np.mgrid[0:300, 0:300]
    m = ((xx - 150) ** 2 + (yy - 150) ** 2) < 120 ** 2
    pts = mask_to_polygon(m, max_points=6)
    assert pts is not None and 3 <= len(pts) <= 6


def test_max_points_below_three_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        mask_to_polygon(_square(), max_points=2)


def test_non_bool_mask_is_accepted():
    # float/uint8 prediction maps should work via the internal bool cast.
    m = np.zeros((200, 200), dtype=np.float32)
    m[40:160, 40:160] = 1.0
    pts = mask_to_polygon(m)
    assert pts is not None and len(pts) >= 3


def test_thin_line_returns_none():
    # A 1-px-tall line clears the area floor but yields < 3 contour points.
    m = np.zeros((400, 400), dtype=bool)
    m[200:201, 10:390] = True
    assert mask_to_polygon(m) is None
