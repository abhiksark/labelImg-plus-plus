from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from libs.core.video_sam2 import (
    ConfiguredPropagationBackend, Sam2Availability,
    Sam2PropagationBackend, inspect_sam2_environment,
    normalize_propagation_backend,
)
from libs.core.video_types import (
    ObservationRecord, PropagationRequest, VideoFingerprint,
)


class _Distribution:
    def read_text(self, name):
        assert name == 'direct_url.json'
        return '{"url":"file:///src/sam2","dir_info":{"editable":true}}'


def test_backend_name_normalization_is_stable():
    assert normalize_propagation_backend(None) == 'auto'
    assert normalize_propagation_backend(' SAM2 ') == 'sam2'
    assert normalize_propagation_backend('opencv') == 'opencv'
    assert normalize_propagation_backend('future-backend') == 'auto'


def test_environment_short_circuits_before_optional_imports():
    loader = Mock(side_effect=AssertionError('must remain lazy'))
    result = inspect_sam2_environment('', '', module_loader=loader)
    assert result.available is False
    assert 'checkpoint' in result.message
    assert 'model-config' in result.message
    loader.assert_not_called()


def test_environment_accepts_compatible_source_install(tmp_path):
    checkpoint = tmp_path / 'model.pt'
    package = tmp_path / 'sam2'
    config = package / 'configs' / 'model.yaml'
    config.parent.mkdir(parents=True)
    checkpoint.write_bytes(b'checkpoint')
    config.write_text('model: fake', encoding='utf-8')
    module_file = package / '__init__.py'
    module_file.write_text('', encoding='utf-8')
    torch = SimpleNamespace(
        __version__='2.5.1+cu124',
        cuda=SimpleNamespace(is_available=lambda: True))
    build = SimpleNamespace(build_sam2_video_predictor=lambda: None)

    def load(name):
        return {
            'torch': torch,
            'torchvision': SimpleNamespace(__version__='0.20.1+cu124'),
            'sam2': SimpleNamespace(__file__=str(module_file)),
            'sam2.build_sam': build,
        }[name]

    result = inspect_sam2_environment(
        str(checkpoint), str(config), module_loader=load,
        metadata_lookup=lambda _name: _Distribution(),
        system='Linux', version_info=(3, 10))
    assert result == Sam2Availability(True)


def test_explicit_unavailable_sam2_never_falls_back():
    backend = ConfiguredPropagationBackend('sam2', '/missing.pt', '/missing')
    with patch(
            'libs.core.video_sam2.inspect_sam2_environment',
            return_value=Sam2Availability(False, ('CUDA is unavailable',))), \
            patch.object(backend, '_opencv') as opencv:
        with pytest.raises(RuntimeError, match='Select OpenCV or Auto'):
            backend.propagate(None, 1, lambda: False, lambda _batch: None)
    opencv.assert_not_called()


def test_auto_falls_back_to_portable_backend():
    expected = object()
    portable = Mock()
    portable.propagate.return_value = expected
    backend = ConfiguredPropagationBackend('auto', '/missing.pt', '/missing')
    with patch(
            'libs.core.video_sam2.inspect_sam2_environment',
            return_value=Sam2Availability(False, ('not configured',))), \
            patch.object(backend, '_opencv', return_value=portable):
        assert backend.propagate(
            'request', 1, lambda: False, lambda _batch: None) is expected
    portable.propagate.assert_called_once()


class _FakeMask:
    def __init__(self, value):
        self.value = value

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.value


class _FakeCuda:
    def __init__(self):
        self.empty_calls = 0

    def empty_cache(self):
        self.empty_calls += 1


class _FakeTorchRuntime:
    def __init__(self, cuda):
        self.cuda = cuda
        self.workspaces_cleared = False
        self._C = SimpleNamespace(
            _cuda_clearCublasWorkspaces=self._clear_workspaces)

    def _clear_workspaces(self):
        self.workspaces_cleared = True

    @staticmethod
    def inference_mode():
        return nullcontext()


class _FakePredictor:
    def __init__(self, np):
        self.np = np
        self.prompts = []
        self.reset = False
        self.embedding = SimpleNamespace(cache={'position': object()})

    def init_state(self, **kwargs):
        assert Path(kwargs['video_path']).is_dir()
        assert kwargs['offload_video_to_cpu'] is True
        return {'ready': True}

    def add_new_mask(self, **kwargs):
        self.prompts.append((
            kwargs['obj_id'], kwargs['frame_idx'], kwargs['mask']))

    def propagate_in_video(self, _state, **kwargs):
        assert kwargs == {
            'start_frame_idx': 0,
            'max_frame_num_to_track': 5,
            'reverse': False,
        }
        rectangle = self.np.full((1, 1, 12, 16), -1.0)
        rectangle[..., 2:8, 3:10] = 2.0
        polygon = self.np.full((1, 1, 12, 16), -1.0)
        polygon[..., 2:9, 5:11] = 2.0
        empty = self.np.full((1, 1, 12, 16), -1.0)
        yield 0, ['rect', 'poly'], [
            _FakeMask(rectangle), _FakeMask(polygon)]
        yield 1, ['rect', 'poly'], [
            _FakeMask(rectangle), _FakeMask(polygon)]
        yield 2, ['rect', 'poly'], [
            _FakeMask(empty), _FakeMask(polygon)]
        yield 3, ['rect', 'poly'], [
            _FakeMask(rectangle), _FakeMask(polygon)]
        yield 4, ['rect', 'poly'], [
            _FakeMask(rectangle), _FakeMask(polygon)]
        yield 5, ['rect', 'poly'], [
            _FakeMask(rectangle), _FakeMask(polygon)]

    def reset_state(self, state):
        assert state == {'ready': True}
        self.reset = True

    def modules(self):
        return (self, self.embedding)


def test_sam2_adapter_converts_masks_and_records_no_object_gap(tmp_path):
    np = pytest.importorskip('numpy')
    cv2 = pytest.importorskip('cv2')
    package = tmp_path / 'sam2'
    config_dir = package / 'configs'
    config_dir.mkdir(parents=True)
    config = config_dir / 'model.yaml'
    checkpoint = tmp_path / 'model.pt'
    config.write_text('model: fake', encoding='utf-8')
    checkpoint.write_bytes(b'checkpoint')
    module_file = package / '__init__.py'
    module_file.write_text('', encoding='utf-8')
    predictor = _FakePredictor(np)
    cuda = _FakeCuda()
    torch = _FakeTorchRuntime(cuda)
    fingerprint = VideoFingerprint(10, 20, 'same')
    rectangle = ObservationRecord(
        'rect', 0, [1, 1, 8, 8], keypoints=[[2, 2, 2]],
        source='manual', review_state='accepted', anchor=True)
    polygon = ObservationRecord(
        'poly', 0, [[1, 1], [8, 1], [8, 8], [1, 8]],
        source='manual', review_state='accepted', anchor=True)
    later_anchor = ObservationRecord(
        'rect', 40, [4, 2, 10, 7], keypoints=[[5, 3, 2]],
        source='manual', review_state='accepted', anchor=True)
    request = PropagationRequest(
        request_id=7, generation=2, document_revision=4,
        source_path=str(tmp_path / 'video.mp4'), fingerprint=fingerprint,
        stream_index=0, time_base_num=1, time_base_den=10,
        start_pts=0, end_pts=50, current_pts=0, direction=1,
        seeds=(rectangle, polygon), manual_anchors=(later_anchor,),
        track_revisions=(('poly', 4), ('rect', 4)),
        average_rate_num=10, average_rate_den=1)
    batches = []

    with patch(
            'libs.core.video_sam2.inspect_sam2_environment',
            return_value=Sam2Availability(True)), patch(
                'libs.core.video_sam2.fingerprint_video',
                return_value=fingerprint), patch(
                    'libs.core.video_sam2._extract_frames',
                    return_value=((0, 10, 20, 30, 40, 50), 16, 12)), patch(
                        'libs.core.video_sam2._load_sam2_runtime',
                        return_value=(
                            torch, np, cv2,
                            SimpleNamespace(__file__=str(module_file)),
                            lambda *_args, **_kwargs: predictor)):
        result = Sam2PropagationBackend(
            str(checkpoint), str(config)).propagate(
                request, 1, lambda: False, batches.append)

    rectangle_results = [
        item for item in result.observations if item.track_id == 'rect']
    polygon_results = [
        item for item in result.observations if item.track_id == 'poly']
    assert len(rectangle_results) == 2
    assert rectangle_results[0].geometry == [3.0, 2.0, 10.0, 8.0]
    assert rectangle_results[0].keypoints[0][0] > 2
    assert [item.pts for item in rectangle_results] == [10, 50]
    assert len(polygon_results) == 5
    assert all(len(item.geometry) >= 4 for item in polygon_results)
    assert result.gaps == (
        result.gaps[0].__class__('rect', 20, 30, 'occluded', 'sam2', 4),)
    assert result.failures == (('rect', 'occluded'),)
    assert all(item.source == 'tracker' and item.review_state == 'accepted'
               and not item.anchor for item in result.observations)
    assert batches[-1].finished is True
    assert batches[-1].completed_tracks == 0
    assert any(batch.completed_tracks == 1 for batch in batches[:-1])
    assert {item[0] for item in predictor.prompts} == {'rect', 'poly'}
    assert predictor.reset is True
    assert predictor.embedding.cache == {}
    assert cuda.empty_calls == 2
    assert torch.workspaces_cleared is True
