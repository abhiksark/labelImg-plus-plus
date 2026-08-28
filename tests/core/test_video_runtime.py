from libs.core.video_runtime import probe_video_runtime


def test_runtime_probe_names_missing_components_without_importing_them(
        monkeypatch):
    looked_up = []

    def find_spec(name):
        looked_up.append(name)
        return None if name == 'av' else object()

    monkeypatch.setattr(
        'libs.core.video_runtime.importlib.util.find_spec', find_spec)

    status = probe_video_runtime()

    assert looked_up == ['av', 'numpy']
    assert status.available is False
    assert status.missing == ('av',)
    assert status.install_command == 'pip install "labelimgplusplus[video]"'
    assert status.detail == 'Missing optional component: av'


def test_runtime_probe_reports_ready_when_every_component_is_available(
        monkeypatch):
    monkeypatch.setattr(
        'libs.core.video_runtime.importlib.util.find_spec',
        lambda _name: object())

    status = probe_video_runtime()

    assert status.available is True
    assert status.missing == ()
    assert status.detail == 'Ready'


def test_video_open_session_uses_dependencies_prefetched_by_gui(
        monkeypatch, tmp_path):
    from libs.core.video_session import prepare_video_open

    dependencies = (object(), object())

    class FakeDecoder(object):
        def __init__(self, source_path, stream_index=None, cancelled=None,
                     dependencies=None):
            self.source_path = source_path
            self.dependencies = dependencies

        def decode_first(self, cancelled=None):
            return object()

        def snapshot(self, project_path, initial, revision=0,
                     read_only=False):
            return object()

        def close(self):
            pass

    monkeypatch.setattr(
        'libs.core.video_session.VideoDecoderSession', FakeDecoder)

    prepared = prepare_video_open(
        str(tmp_path / 'clip.mp4'), read_only=True,
        dependencies=dependencies)

    assert prepared.decoder.dependencies is dependencies
