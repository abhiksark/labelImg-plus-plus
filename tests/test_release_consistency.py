"""Regression tests for release-version consistency."""

from email.parser import Parser
from pathlib import Path
import re

from libs import __version__, __version_info__


ROOT = Path(__file__).resolve().parents[1]


def _project_version():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(
        r"^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)",
        pyproject,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert project is not None, "pyproject.toml has no [project] table"

    version = re.search(
        r'^version\s*=\s*["\'](?P<value>[^"\']+)["\']\s*$',
        project.group("body"),
        flags=re.MULTILINE,
    )
    assert version is not None, "[project] has no static version"
    return version.group("value")


def _tracked_metadata_version():
    pkg_info = (ROOT / "labelimgplusplus.egg-info" / "PKG-INFO").read_text(
        encoding="utf-8"
    )
    return Parser().parsestr(pkg_info)["Version"]


def _sonar_version():
    properties = (ROOT / "sonar-project.properties").read_text(
        encoding="utf-8"
    )
    version = re.search(
        r"^sonar\.projectVersion=(?P<value>\S+)\s*$",
        properties,
        flags=re.MULTILINE,
    )
    assert version is not None, "sonar-project.properties has no project version"
    return version.group("value")


def test_release_versions_are_consistent():
    project_version = _project_version()

    assert __version__ == project_version
    assert __version_info__ == tuple(project_version.split("."))
    assert _tracked_metadata_version() == project_version
    assert _sonar_version() == project_version
