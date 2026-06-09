# tests/tools/test_demo_setup.py
"""Tests for the demo-GIF workspace helper."""

import json
import os
import sys
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'scripts'))

import pytest

# build_workspace renders the demo images with Pillow, a maintainer-only
# dependency absent from CI. Skip rather than fail when it isn't installed.
pytest.importorskip("PIL")

import _demo_setup


def test_build_workspace_creates_dirs_images_and_classes(tmp_path):
    info = _demo_setup.build_workspace(str(tmp_path))
    assert os.path.isdir(info['image_dir'])
    assert os.path.isdir(info['save_dir'])
    assert info['num_images'] >= 1
    assert os.path.isfile(info['first_image'])
    # every file reported in the image dir actually exists
    for name in os.listdir(info['image_dir']):
        assert os.path.isfile(os.path.join(info['image_dir'], name))
    with open(info['classes']) as f:
        classes = f.read().split()
    assert 'cat' in classes   # the subject of the tour
    assert 'face' in classes  # the keypoint-template label


def test_workspace_cli_emits_json(tmp_path):
    out = subprocess.check_output(
        [sys.executable, os.path.join(REPO, 'scripts', '_demo_setup.py'),
         'workspace', str(tmp_path)])
    info = json.loads(out)
    assert info['image_dir'] and info['classes'] and info['save_dir']
