from types import SimpleNamespace

from libs.core.plugin_discovery import (
    ENTRY_POINT_GROUP,
    discover_plugins,
    select_plugin_entry_points,
)


class _Selectable(list):
    def select(self, **params):
        return _Selectable([
            ep for ep in self
            if all(getattr(ep, key) == value for key, value in params.items())
        ])


def _dist(name="example-plugin", version="1.2.3", entry_points=()):
    return SimpleNamespace(
        metadata={"Name": name}, version=version, entry_points=entry_points)


def _entry(name, value="example:factory", dist=True, group=ENTRY_POINT_GROUP):
    fields = {"name": name, "value": value, "group": group}
    if dist:
        fields["dist"] = _dist()
    return SimpleNamespace(**fields)


def test_selects_legacy_mapping_and_iterable_collections():
    plugin = _entry("com.example.plugin")
    other = _entry("other", group="console_scripts")
    assert select_plugin_entry_points({ENTRY_POINT_GROUP: [plugin]}) == (plugin,)
    assert select_plugin_entry_points([other, plugin]) == (plugin,)


def test_selects_modern_collection_without_tuple_access():
    plugin = _entry("com.example.plugin")
    collection = _Selectable([plugin, _entry("other", group="other")])
    assert select_plugin_entry_points(collection) == (plugin,)


def test_discovery_is_deterministic_and_does_not_load_entry_points():
    loaded = []
    entries = _Selectable([
        _entry("z.plugin"),
        _entry("a_plugin"),
        _entry("m-plugin"),
    ])
    for entry in entries:
        entry.load = lambda: loaded.append(entry.name)

    result = discover_plugins(lambda: entries)

    assert [candidate.id for candidate in result] == [
        "a_plugin", "m-plugin", "z.plugin"]
    assert loaded == []
    assert all(candidate.loadable for candidate in result)


def test_duplicate_ids_disable_every_candidate():
    first = _entry("same.plugin", "first:create")
    second = _entry("same.plugin", "second:create")
    second.dist = _dist("second-distribution", "2.0")

    result = discover_plugins(lambda: [second, first])

    assert len(result) == 2
    assert all(not candidate.loadable for candidate in result)
    assert all(
        "duplicate_plugin_id" in {item.code for item in candidate.diagnostics}
        for candidate in result
    )


def test_invalid_id_and_missing_provider_are_diagnostics():
    candidate, = discover_plugins(
        lambda: [_entry("Invalid ID", dist=False)],
        distributions_provider=lambda: (),
    )
    assert {item.code for item in candidate.diagnostics} == {
        "invalid_plugin_id", "missing_provider_metadata"}
    assert not candidate.loadable


def test_legacy_entry_point_provider_is_resolved_from_distribution():
    entry = _entry("com.example.legacy", dist=False)
    provider = _dist("legacy-provider", "4.5.6", [entry])

    candidate, = discover_plugins(
        lambda: {ENTRY_POINT_GROUP: [entry]},
        distributions_provider=lambda: [provider],
    )

    assert candidate.distribution == "legacy-provider"
    assert candidate.distribution_version == "4.5.6"
    assert candidate.loadable


def test_public_api_import_is_qt_free_in_clean_interpreter(tmp_path):
    import os
    import subprocess
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    code = (
        "import sys; import labelimgplusplus.plugins; "
        "assert not any(name.startswith('PyQt') for name in sys.modules); "
        "assert 'numpy' not in sys.modules; assert 'cv2' not in sys.modules; "
        "assert 'av' not in sys.modules"
    )
    subprocess.run(
        [sys.executable, "-c", code], cwd=root, check=True,
        env={**os.environ, "PYTHONPATH": root},
    )


def test_package_configuration_includes_public_namespace():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    config = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["libs*", "labelimgplusplus*"]' in config
