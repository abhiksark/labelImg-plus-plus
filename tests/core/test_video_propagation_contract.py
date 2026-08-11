from dataclasses import FrozenInstanceError
import json
import subprocess
import sys

import pytest

from libs.core.video_propagation import PropagationBackend
from libs.core.video_types import (
    ObservationRecord, PropagationBatch, PropagationRequest,
    PropagationResult, TrackGapRecord, VideoFingerprint,
)


def _request():
    fingerprint = VideoFingerprint(100, 20, 'abc')
    seed = ObservationRecord('track-1', 10, (1, 2, 3, 4))
    return PropagationRequest(
        request_id=7, generation=8, document_revision=9,
        source_path='/media/clip.mp4', fingerprint=fingerprint,
        stream_index=0, time_base_num=1, time_base_den=30,
        start_pts=0, end_pts=90, current_pts=10, direction=1,
        seeds=(seed,), manual_anchors=(seed,),
        track_revisions=(('track-1', 9),))


def test_propagation_contracts_are_frozen_plain_data():
    request = _request()
    gap = TrackGapRecord(
        'track-1', 11, 20, 'occluded', 'opencv', revision=10)
    batch = PropagationBatch(
        7, 8, 1, gaps=(gap,), processed_frames=4, total_frames=20,
        active_tracks=1, completed_tracks=0, eta_seconds=1.5)
    result = PropagationResult(
        7, 8, 9, gaps=(gap,), failures=(('track-2', 'scene_cut'),))

    assert request.manual_anchors == request.seeds
    assert batch.gaps == (gap,)
    assert result.failures == (('track-2', 'scene_cut'),)
    with pytest.raises(FrozenInstanceError):
        gap.reason = 'changed'
    with pytest.raises(FrozenInstanceError):
        request.direction = -1


def test_contract_and_backend_modules_do_not_import_qt_or_optionals():
    script = """
import json
import sys
import libs.core.video_types
import libs.core.video_propagation
print(json.dumps(sorted(sys.modules)))
"""
    process = subprocess.run(
        [sys.executable, '-c', script], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    imported = set(json.loads(process.stdout))
    assert not any(name.startswith('PyQt') for name in imported)
    assert 'av' not in imported
    assert 'cv2' not in imported
    assert 'numpy' not in imported


def test_backend_interface_is_explicit_and_stateless():
    backend = PropagationBackend()
    assert backend.__dict__ == {}
    with pytest.raises(NotImplementedError):
        backend.propagate(_request(), 1, lambda: False, lambda _batch: None)
