import importlib.util
import os
from pathlib import Path
import shutil

import pytest

from libs.core.video_decoder import VideoDecoderSession


_GENERATOR_PATH = Path(__file__).parents[2] / 'tools' / 'performance' / \
    'generate_workload.py'
_SPEC = importlib.util.spec_from_file_location(
    'labelimgpp_generate_workload', _GENERATOR_PATH)
_GENERATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_GENERATOR)
generate_video_workload = _GENERATOR.generate_video_workload


def test_smoke_workload_covers_media_acceptance_matrix(tmp_path):
    pytest.importorskip('av')
    pytest.importorskip('numpy')
    paths = generate_video_workload(str(tmp_path), profile='smoke')
    names = {os.path.basename(path) for path in paths}
    assert {'cfr.mp4', 'cfr.avi', 'vfr.mkv', 'long-gop.mp4',
            'rotated.mov', 'navigation-4k.mp4', 'navigation-8k.mkv',
            'tracking-stress.mp4'} <= names
    assert (tmp_path / 'video' / 'switch-image.jpg').is_file()

    for path in paths:
        decoder = VideoDecoderSession(path)
        try:
            assert not decoder.decode_first().image.isNull()
        finally:
            decoder.close()

    if shutil.which('ffmpeg'):
        rotated = VideoDecoderSession(str(tmp_path / 'video' / 'rotated.mov'))
        try:
            frame = rotated.decode_first()
            assert frame.rotation == 90
            assert frame.display_width == frame.original_height
        finally:
            rotated.close()

    with open(tmp_path / 'video' / 'manifest.json', encoding='utf-8') as stream:
        manifest = stream.read()
    assert '"profile": "smoke"' in manifest
