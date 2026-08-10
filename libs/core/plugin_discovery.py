"""Metadata-only discovery for installed labelImg++ plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
import re
from typing import Optional, Tuple

from labelimgplusplus.plugins import PluginDiagnostic


ENTRY_POINT_GROUP = "labelimgplusplus.plugins"
_VALID_PLUGIN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")
_NORMALIZE_ID = re.compile(r"[-_.]+")


def is_valid_plugin_id(plugin_id):
    """Return whether *plugin_id* is a valid canonical entry-point name."""
    return isinstance(plugin_id, str) and bool(_VALID_PLUGIN_ID.fullmatch(plugin_id))


def normalized_plugin_id(plugin_id):
    """Return a deterministic comparison key for a plugin ID."""
    return _NORMALIZE_ID.sub("-", plugin_id).lower()


@dataclass(frozen=True)
class PluginCandidate:
    """An entry point plus provider data, without importing plugin code."""

    id: str
    reference: str
    distribution: Optional[str]
    distribution_version: Optional[str]
    entry_point: object = field(compare=False, repr=False)
    diagnostics: Tuple[PluginDiagnostic, ...] = ()

    @property
    def loadable(self):
        return not self.diagnostics


def select_plugin_entry_points(collection):
    """Adapt legacy mapping/list and modern selectable entry-point results."""
    select = getattr(collection, "select", None)
    if callable(select):
        return tuple(select(group=ENTRY_POINT_GROUP))
    if isinstance(collection, dict):
        return tuple(collection.get(ENTRY_POINT_GROUP, ()))
    return tuple(
        entry_point for entry_point in collection
        if getattr(entry_point, "group", None) == ENTRY_POINT_GROUP
    )


def _provider_from_entry_point(entry_point):
    distribution = getattr(entry_point, "dist", None)
    if distribution is None:
        return None, None
    dist_metadata = getattr(distribution, "metadata", {})
    name = None
    try:
        name = dist_metadata.get("Name")
    except AttributeError:
        pass
    version = getattr(distribution, "version", None)
    return name, version


def _provider_index(distributions):
    """Index distributions for Python versions whose EntryPoint lacks .dist."""
    result = {}
    for distribution in distributions:
        dist_metadata = getattr(distribution, "metadata", {})
        try:
            name = dist_metadata.get("Name")
        except AttributeError:
            name = None
        version = getattr(distribution, "version", None)
        for entry_point in getattr(distribution, "entry_points", ()):
            if getattr(entry_point, "group", None) != ENTRY_POINT_GROUP:
                continue
            key = (
                getattr(entry_point, "name", None),
                getattr(entry_point, "value", None),
            )
            result.setdefault(key, []).append((name, version))
    return result


def discover_plugins(entry_points_provider=None, distributions_provider=None):
    """Discover plugin candidates without importing their target modules.

    Providers are injectable to exercise the Python 3.8/3.9 and 3.10+
    metadata collection shapes without patching global package metadata.
    """
    entry_points_provider = entry_points_provider or metadata.entry_points
    distributions_provider = distributions_provider or metadata.distributions
    entry_points = select_plugin_entry_points(entry_points_provider())

    missing_provider = [
        entry_point for entry_point in entry_points
        if _provider_from_entry_point(entry_point)[0] is None
    ]
    fallback = {}
    if missing_provider:
        fallback = _provider_index(distributions_provider())

    candidates = []
    for entry_point in entry_points:
        plugin_id = getattr(entry_point, "name", "")
        reference = getattr(entry_point, "value", "")
        provider_name, provider_version = _provider_from_entry_point(entry_point)
        if provider_name is None:
            providers = fallback.get((plugin_id, reference), ())
            if len(providers) == 1:
                provider_name, provider_version = providers[0]

        diagnostics = []
        if not is_valid_plugin_id(plugin_id):
            diagnostics.append(PluginDiagnostic(
                plugin_id=plugin_id or "<unknown>",
                phase="discovery",
                code="invalid_plugin_id",
                message=("Plugin IDs must use lowercase letters, digits, dots, "
                         "underscores, and hyphens."),
            ))
        if not provider_name or not provider_version:
            diagnostics.append(PluginDiagnostic(
                plugin_id=plugin_id or "<unknown>",
                phase="discovery",
                code="missing_provider_metadata",
                message="The entry point has no complete provider name/version metadata.",
            ))
        candidates.append(PluginCandidate(
            id=plugin_id,
            reference=reference,
            distribution=provider_name,
            distribution_version=provider_version,
            entry_point=entry_point,
            diagnostics=tuple(diagnostics),
        ))

    by_id = {}
    for candidate in candidates:
        by_id.setdefault(candidate.id, []).append(candidate)
    conflicts = {plugin_id for plugin_id, group in by_id.items() if len(group) > 1}
    if conflicts:
        updated = []
        for candidate in candidates:
            if candidate.id not in conflicts:
                updated.append(candidate)
                continue
            diagnostic = PluginDiagnostic(
                plugin_id=candidate.id,
                phase="discovery",
                code="duplicate_plugin_id",
                message="Multiple installed distributions claim this plugin ID.",
            )
            updated.append(PluginCandidate(
                id=candidate.id,
                reference=candidate.reference,
                distribution=candidate.distribution,
                distribution_version=candidate.distribution_version,
                entry_point=candidate.entry_point,
                diagnostics=candidate.diagnostics + (diagnostic,),
            ))
        candidates = updated

    return tuple(sorted(
        candidates,
        key=lambda item: (
            normalized_plugin_id(item.id),
            item.id,
            item.distribution or "",
            item.reference,
        ),
    ))


__all__ = [
    "ENTRY_POINT_GROUP",
    "PluginCandidate",
    "discover_plugins",
    "is_valid_plugin_id",
    "normalized_plugin_id",
    "select_plugin_entry_points",
]
