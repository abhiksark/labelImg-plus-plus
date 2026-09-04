# ex: set ts=8 noet:

all: test

test:
	QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -v

clean:
	rm -rf ~/.labelImgSettings.json ~/.labelImgSettings.pkl *.pyc dist labelImg.egg-info __pycache__ build

pip_upload:
	python3 setup.py upload

long_description:
	restview --long-description

.PHONY: all test testpy3
