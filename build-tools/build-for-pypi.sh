#!/bin/sh
# Build and upload labelImgPlusPlus to PyPI

set -e

echo "Building labelImgPlusPlus for PyPI..."

# Clean previous builds
rm -rf build dist *.egg-info

# Build package
python -m build

echo ""
echo "Build complete! Files in dist/:"
ls -la dist/

echo ""
while true; do
    read -p "Do you wish to upload to PyPI? (y/n) " yn
    case $yn in
        [Yy]* ) twine upload dist/*; break;;
        [Nn]* ) echo "Skipping upload."; exit;;
        * ) echo "Please answer yes or no.";;
    esac
done

# Test install: pip install dist/labelImgPlusPlus-*.whl
