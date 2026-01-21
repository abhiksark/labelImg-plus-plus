#!/bin/bash
### Windows build script using pyinstaller

THIS_SCRIPT_PATH=`readlink -f $0`
THIS_SCRIPT_DIR=`dirname ${THIS_SCRIPT_PATH}`
cd ${THIS_SCRIPT_DIR}

rm -rf build
rm -rf dist
rm -f labelImgPlusPlus.spec

pyinstaller --hidden-import=xml \
            --hidden-import=xml.etree \
            --hidden-import=xml.etree.ElementTree \
            --hidden-import=lxml.etree \
            --hidden-import=pyqt5 \
            -D -F -n labelImgPlusPlus -c "../labelImg.py" -p ../libs -p ../

FOLDER=$(git describe --abbrev=0 --tags)
FOLDER="windows_"$FOLDER
rm -rf "$FOLDER"
mkdir "$FOLDER"
cp dist/labelImgPlusPlus.exe $FOLDER
cp -rf ../data $FOLDER/data
zip "$FOLDER.zip" -r $FOLDER
