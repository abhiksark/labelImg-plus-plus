# tests/video/test_distinctness_worker.py
"""The pixel pass only ever adds frames, and stays inside its decode budget."""
import pytest

pytest.importorskip('av')
pytest.importorskip('numpy')

from libs.core.video_distinctness_worker import (  # noqa: E402
    refine_distinct_pts, stride_for)
from libs.core.video_model import VideoModelState  # noqa: E402


def test_stride_bounds_decode_count():
    """A 30fps clip at 2 frames/second decodes every 15th frame."""
    assert stride_for(30.0, 2.0) == 15
    assert stride_for(60.0, 2.0) == 30
    assert stride_for(1.0, 2.0) == 1          # never below 1
    assert stride_for(None, 2.0) == 1         # unknown rate degrades safely


def test_refinement_is_additive(make_video, tmp_path):
    """Every geometry frame survives, and the result stays sorted."""
    path = make_video(tmp_path / 'clip.mp4', frames=24)
    state = VideoModelState((), (), (), ())
    seeded = (0, 5)
    result = refine_distinct_pts(
        path, 0, state, seeded, fps=12.0, max_per_second=2.0)
    assert set(seeded).issubset(set(result))
    assert list(result) == sorted(result)


def test_cancellation_returns_the_geometry_answer(make_video, tmp_path):
    """A cancelled pass degrades to its input rather than failing."""
    path = make_video(tmp_path / 'clip.mp4', frames=24)
    state = VideoModelState((), (), (), ())
    result = refine_distinct_pts(
        path, 0, state, (0, 5), fps=12.0,
        cancelled=lambda: True)
    assert result == (0, 5)
