#!/usr/bin/env python3
"""Verify that every resources.qrc alias exists in the generated module."""

from pathlib import Path
import sys
from xml.etree import ElementTree

from PyQt5.QtCore import QResource


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    # Importing the generated module registers its compiled resource table.
    from libs import resources  # noqa: F401

    root = ElementTree.parse(str(ROOT / "resources.qrc")).getroot()
    aliases = []
    missing_sources = []
    for file_element in root.iter("file"):
        source = (file_element.text or "").strip()
        alias = file_element.get("alias") or source
        aliases.append(alias)
        if not (ROOT / source).is_file():
            missing_sources.append(source)

    missing_aliases = [
        alias for alias in aliases if not QResource(":/" + alias).isValid()
    ]
    if missing_sources or missing_aliases:
        if missing_sources:
            print(
                "missing qrc source files: " + ", ".join(missing_sources),
                file=sys.stderr,
            )
        if missing_aliases:
            print(
                "missing generated resource aliases: "
                + ", ".join(missing_aliases),
                file=sys.stderr,
            )
        return 1

    print("verified {} Qt resource aliases".format(len(aliases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
