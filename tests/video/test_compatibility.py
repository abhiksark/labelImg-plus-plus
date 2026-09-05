import os
import subprocess
import sys

from libs.core.video_decoder import VIDEO_INSTALL_HINT


def test_video_dependency_markers_cover_each_python_line():
    with open('pyproject.toml', 'r', encoding='utf-8') as stream:
        metadata = stream.read()
    assert 'av>=17.1,<18; python_version == \'3.10\'' in metadata
    assert 'av>=18,<19; python_version >= \'3.11\'' in metadata
    assert metadata.count('opencv-python-headless>=4.8,<6') == 2
    lowered = metadata.lower()
    assert '"torch' not in lowered
    assert '"sam-2' not in lowered
    assert '"sam2' not in lowered


def test_base_application_imports_without_optional_video_modules():
    script = r'''
import builtins
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.', 1)[0] in (
            'av', 'cv2', 'numpy', 'torch', 'torchvision', 'sam2'):
        raise AssertionError('optional video module imported at base startup')
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
import labelImgPlusPlus
from libs.core.video_decoder import VIDEO_INSTALL_HINT
assert '[video]' in VIDEO_INSTALL_HINT
'''
    environment = os.environ.copy()
    environment.setdefault('QT_QPA_PLATFORM', 'offscreen')
    subprocess.run(
        [sys.executable, '-c', script], check=True,
        cwd=os.path.abspath(os.curdir), env=environment)


def test_install_hint_names_the_optional_extra():
    assert 'labelimgplusplus[video]' in VIDEO_INSTALL_HINT
