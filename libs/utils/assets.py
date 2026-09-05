"""Resolve packaged runtime assets without importing a Qt binding."""

import re
from pathlib import Path
from types import MappingProxyType
from typing import Optional


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets"

ICON_FILES = MappingProxyType({
    "help": "icons/feather/help-circle.svg",
    "expert": "icons/feather/sliders.svg",
    "done": "icons/feather/check.svg",
    "file": "icons/feather/file.svg",
    "labels": "icons/feather/grid.svg",
    "new": "icons/feather/plus-square.svg",
    "close": "icons/feather/x.svg",
    "fit-width": "icons/feather/maximize.svg",
    "fit-window": "icons/feather/maximize-2.svg",
    "undo": "icons/feather/rotate-ccw.svg",
    "redo": "icons/feather/rotate-cw.svg",
    "hide": "icons/feather/eye-off.svg",
    "quit": "icons/feather/log-out.svg",
    "copy": "icons/feather/copy.svg",
    "edit": "icons/feather/edit-3.svg",
    "open": "icons/feather/folder.svg",
    "save": "icons/feather/save.svg",
    "save-as": "icons/feather/download.svg",
    "color": "icons/feather/droplet.svg",
    "color_line": "icons/feather/edit-2.svg",
    "zoom": "icons/feather/search.svg",
    "zoom-in": "icons/feather/zoom-in.svg",
    "zoom-out": "icons/feather/zoom-out.svg",
    "sun": "icons/feather/sun.svg",
    "light_reset": "icons/feather/sun.svg",
    "light_lighten": "icons/feather/sun.svg",
    "light_darken": "icons/feather/moon.svg",
    "delete": "icons/feather/trash-2.svg",
    "next": "icons/feather/chevron-right.svg",
    "prev": "icons/feather/chevron-left.svg",
    "chevron-down": "icons/feather/chevron-down.svg",
    "chevron-up": "icons/feather/chevron-up.svg",
    "resetall": "icons/feather/refresh-cw.svg",
    "verify": "icons/feather/check-circle.svg",
    "settings": "icons/feather/settings.svg",
    "tool-select": "icons/feather/mouse-pointer.svg",
    "tool-box": "icons/feather/square.svg",
    "tool-polygon": "icons/feather/hexagon.svg",
    "tool-smart-select": "icons/feather/crosshair.svg",
    "tool-keypoints": "icons/feather/share-2.svg",
    "app": "icons/app.png",
    "format_voc": "icons/format_voc.png",
    "format_yolo": "icons/format_yolo.png",
    "format_createml": "icons/format_createml.png",
})

STRING_FILES = MappingProxyType({
    "strings": "strings/strings.properties",
    "strings-ja-JP": "strings/strings-ja-JP.properties",
    "strings-zh-CN": "strings/strings-zh-CN.properties",
    "strings-zh-TW": "strings/strings-zh-TW.properties",
})

LICENSE_FILES = MappingProxyType({
    "feather-license": "licenses/feather.txt",
})

_BUNDLE_NAME = re.compile(r"^strings(?:-[A-Za-z0-9]+){0,2}$")


def _existing_path(relative_name: str) -> Path:
    path = ASSET_ROOT / relative_name
    if not path.is_file():
        raise FileNotFoundError("packaged asset is missing: %s" % relative_name)
    return path


def icon_path(name: str) -> str:
    """Return the filesystem path for a semantic icon name."""
    try:
        relative_name = ICON_FILES[name]
    except KeyError:
        raise KeyError("unknown icon: %s" % name) from None
    return str(_existing_path(relative_name))


def read_string_bundle(
        bundle_name: str, required: bool = False) -> Optional[str]:
    """Read one UTF-8 string bundle, or return ``None`` when optional."""
    if not _BUNDLE_NAME.fullmatch(bundle_name):
        raise ValueError("invalid string bundle name: %r" % bundle_name)
    relative_name = STRING_FILES.get(bundle_name)
    if relative_name is None:
        if required:
            raise FileNotFoundError("required string bundle is missing: %s" % bundle_name)
        return None
    try:
        path = _existing_path(relative_name)
    except FileNotFoundError:
        if required:
            raise
        return None
    return path.read_text(encoding="utf-8")


def read_license(name: str) -> str:
    """Read a packaged third-party license as UTF-8 text."""
    try:
        relative_name = LICENSE_FILES[name]
    except KeyError:
        raise KeyError("unknown license: %s" % name) from None
    return _existing_path(relative_name).read_text(encoding="utf-8")


__all__ = [
    "ASSET_ROOT", "ICON_FILES", "STRING_FILES", "LICENSE_FILES",
    "icon_path", "read_string_bundle", "read_license",
]
