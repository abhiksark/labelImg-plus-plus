"""Side-effect-free availability checks for the optional video runtime."""

from dataclasses import dataclass
import importlib.util


VIDEO_INSTALL_COMMAND = 'pip install "labelimgplusplus[video]"'


@dataclass(frozen=True)
class VideoRuntimeStatus:
    available: bool
    missing: tuple
    install_command: str
    detail: str


def probe_video_runtime(required=('av', 'numpy')):
    """Describe optional video support without importing its components."""
    missing = tuple(
        name for name in required if importlib.util.find_spec(name) is None)
    detail = (
        'Ready' if not missing else
        'Missing optional component%s: %s' % (
            '' if len(missing) == 1 else 's', ', '.join(missing)))
    return VideoRuntimeStatus(
        not missing, missing, VIDEO_INSTALL_COMMAND, detail)
