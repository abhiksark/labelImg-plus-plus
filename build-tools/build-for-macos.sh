#!/bin/sh

pip install --upgrade virtualenv

# clone labelImgPlusPlus source
rm -rf /tmp/labelImgPlusPlusSetup
mkdir /tmp/labelImgPlusPlusSetup
cd /tmp/labelImgPlusPlusSetup
curl https://codeload.github.com/abhiksark/labelImg-plus-plus/zip/master --output labelImgPlusPlus.zip
unzip labelImgPlusPlus.zip
rm labelImgPlusPlus.zip

# setup python3 space
virtualenv --system-site-packages -p python3 /tmp/labelImgPlusPlusSetup/venv
source /tmp/labelImgPlusPlusSetup/venv/bin/activate
cd labelImg-plus-plus-master

# build labelImgPlusPlus app
pip install py2app
pip install PyQt5 lxml
make qt5py3
rm -rf build dist
python setup.py py2app -A
mv "/tmp/labelImgPlusPlusSetup/labelImg-plus-plus-master/dist/labelImgPlusPlus.app" /Applications
# deactivate python3
deactivate
cd ../
rm -rf /tmp/labelImgPlusPlusSetup
echo 'DONE'
