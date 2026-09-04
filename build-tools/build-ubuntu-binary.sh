#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(dirname "$SCRIPT_DIR")
cd "$REPOSITORY_ROOT"

export QT_API=pyqt6
python -m PyInstaller --clean --noconfirm build-tools/labelImgPlusPlus.spec
