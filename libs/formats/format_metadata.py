# libs/formats/format_metadata.py
"""Single source of truth for annotation-format display metadata.

Consolidates the per-format data that used to be spread across
``MainWindow.get_format_meta`` (menu title + icon), ``set_format`` (icon, enum,
file suffix) and ``change_format`` (the cycle order + warnings): the identifier
strings (``FORMAT_*``), the :class:`LabelFileFormat` enum, themed-icon names,
menu titles, and file suffixes.

The module holds only data and lookups — no Qt — so it stays unit testable and
free of any dependency on the ``MainWindow`` module.
"""
from collections import namedtuple

from libs.formats.labelFile import LabelFileFormat
from libs.formats.pascal_voc_io import XML_EXT
from libs.formats.yolo_io import TXT_EXT
from libs.formats.create_ml_io import JSON_EXT
from libs.utils.constants import (
    FORMAT_PASCALVOC, FORMAT_YOLO, FORMAT_CREATEML, FORMAT_COCO, FORMAT_YOLO_SEG)

FormatMeta = namedtuple(
    'FormatMeta', ['name', 'enum', 'icon', 'menu_title', 'suffix'])

# Order defines the change_format() cycle.
_FORMATS = [
    FormatMeta(FORMAT_PASCALVOC, LabelFileFormat.PASCAL_VOC,
               'format_voc', '&PascalVOC', XML_EXT),
    FormatMeta(FORMAT_YOLO, LabelFileFormat.YOLO,
               'format_yolo', '&YOLO', TXT_EXT),
    FormatMeta(FORMAT_CREATEML, LabelFileFormat.CREATE_ML,
               'format_createml', '&CreateML', JSON_EXT),
    FormatMeta(FORMAT_COCO, LabelFileFormat.COCO,
               'format_createml', '&COCO', JSON_EXT),
    FormatMeta(FORMAT_YOLO_SEG, LabelFileFormat.YOLO_SEG,
               'format_yolo', '&YOLO-seg', TXT_EXT),
]

_BY_NAME = {m.name: m for m in _FORMATS}
_BY_ENUM = {m.enum: m for m in _FORMATS}

# Warning shown when cycling away from each format (keyed by the format being
# left), preserving the original change_format messages.
_CYCLE_WARNINGS = {
    LabelFileFormat.PASCAL_VOC:
        "Switching to YOLO format.\n\nNote: The 'difficult' flag will be lost.",
    LabelFileFormat.YOLO: "Switching to CreateML format.",
    LabelFileFormat.CREATE_ML:
        "Switching to COCO format.\n\nSupports polygon annotations natively.",
    LabelFileFormat.COCO:
        "Switching to YOLO-seg format.\n\nSupports polygon annotations natively.",
    LabelFileFormat.YOLO_SEG: "Switching to PASCAL VOC format.",
}


def by_name(name):
    """Return the :class:`FormatMeta` for a ``FORMAT_*`` string, or None."""
    return _BY_NAME.get(name)


def meta_for_enum(enum):
    """Return the :class:`FormatMeta` for a ``LabelFileFormat``.

    Falls back to PASCAL VOC for an unknown value, mirroring the old
    ``get_format_meta`` default.
    """
    return _BY_ENUM.get(enum, _FORMATS[0])


#: Order sidecars are searched in when no format prefers otherwise.
DEFAULT_EXTENSION_ORDER = (XML_EXT, TXT_EXT, JSON_EXT)


def extension_order(enum):
    """Return the sidecar search order for an active ``LabelFileFormat``.

    Both the canvas loader and the catalog probe must resolve the same file
    for a given image; when they used different orders, a folder holding both
    a .xml and a .json sidecar showed gallery statuses and thumbnail overlays
    describing one file while the Objects list edited the other.

    Deliberately mirrors what the canvas loader already did rather than
    deriving the order from each format's suffix: only COCO and YOLO-seg
    reordered, and changing that for YOLO or CreateML would alter which
    sidecar an existing mixed-format dataset opens.
    """
    if enum == LabelFileFormat.COCO:
        return (JSON_EXT, XML_EXT, TXT_EXT)
    if enum == LabelFileFormat.YOLO_SEG:
        return (TXT_EXT, XML_EXT, JSON_EXT)
    return DEFAULT_EXTENSION_ORDER


def next_in_cycle(enum):
    """Return ``(next_format_name, warning)`` for cycling from ``enum``.

    Raises :class:`ValueError` for an unknown format, matching the prior
    ``change_format`` behavior.
    """
    if enum not in _BY_ENUM:
        raise ValueError('Unknown label file format.')
    idx = _FORMATS.index(_BY_ENUM[enum])
    nxt = _FORMATS[(idx + 1) % len(_FORMATS)]
    return nxt.name, _CYCLE_WARNINGS[enum]
