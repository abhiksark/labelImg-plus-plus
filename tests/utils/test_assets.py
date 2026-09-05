"""Contracts for package-owned runtime assets."""

import os
import operator
from types import MappingProxyType

import pytest

from libs.utils import assets
from libs.utils.assets import (
    ICON_FILES,
    LICENSE_FILES,
    STRING_FILES,
    icon_path,
    read_license,
    read_string_bundle,
)


def test_asset_catalogs_are_immutable_and_complete():
    assert isinstance(ICON_FILES, MappingProxyType)
    assert isinstance(STRING_FILES, MappingProxyType)
    assert isinstance(LICENSE_FILES, MappingProxyType)
    assert len(ICON_FILES) == 44
    assert set(STRING_FILES) == {
        "strings", "strings-ja-JP", "strings-zh-CN", "strings-zh-TW",
    }
    assert LICENSE_FILES == {"feather-license": "licenses/feather.txt"}
    with pytest.raises(TypeError):
        operator.setitem(ICON_FILES, "other", "icons/other.svg")


def test_every_icon_alias_resolves_outside_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = {name: icon_path(name) for name in ICON_FILES}
    assert all(os.path.isfile(path) for path in paths.values())
    assert paths["sun"] == paths["light_reset"] == paths["light_lighten"]


def test_all_text_assets_decode_as_utf8():
    for name in STRING_FILES:
        contents = read_string_bundle(name, required=True)
        assert contents
        assert "openDir=" in contents
    license_text = read_license("feather-license")
    assert "MIT License" in license_text
    assert "Cole Bemis" in license_text


@pytest.mark.parametrize("name", [
    "", "../strings", "strings/other", "/strings", "C:strings",
    r"strings\\other", "strings-en-US-extra",
])
def test_string_bundle_rejects_invalid_names(name):
    with pytest.raises(ValueError):
        read_string_bundle(name)


def test_optional_unknown_bundle_is_absent():
    assert read_string_bundle("strings-fr-FR") is None
    with pytest.raises(FileNotFoundError):
        read_string_bundle("strings-fr-FR", required=True)


def test_missing_packaged_files_fail_according_to_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "ASSET_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError, match="help-circle.svg"):
        icon_path("help")
    assert read_string_bundle("strings") is None
    with pytest.raises(FileNotFoundError, match="strings.properties"):
        read_string_bundle("strings", required=True)
    with pytest.raises(FileNotFoundError, match="feather.txt"):
        read_license("feather-license")


def test_unknown_semantic_names_raise_key_error():
    with pytest.raises(KeyError, match="unknown icon"):
        icon_path("missing")
    with pytest.raises(KeyError, match="unknown license"):
        read_license("missing")
