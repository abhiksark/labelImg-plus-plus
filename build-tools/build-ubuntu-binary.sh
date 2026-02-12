#!/bin/bash
### Ubuntu use pyinstaller
THIS_SCRIPT_PATH=$(readlink -f "$0")
THIS_SCRIPT_DIR=$(dirname "${THIS_SCRIPT_PATH}")
cd ${THIS_SCRIPT_DIR}

rm -rf build
rm -rf dist
rm -f labelImgPlusPlus.spec
pyinstaller --hidden-import=xml \
            --hidden-import=xml.etree \
            --hidden-import=xml.etree.ElementTree \
            --hidden-import=lxml.etree \
            -D -F -n labelImgPlusPlus -c "../labelImgPlusPlus.py" -p ../libs -p ../

FOLDER=$(git describe --abbrev=0 --tags)
FOLDER="linux_"$FOLDER
rm -rf "$FOLDER"
mkdir "$FOLDER"
cp dist/labelImgPlusPlus $FOLDER
cp -rf ../data $FOLDER/data
zip "$FOLDER.zip" -r $FOLDER
