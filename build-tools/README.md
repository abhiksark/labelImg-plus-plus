# labelImgPlusPlus Build Tools

## Deploy to PyPI

```bash
cd [ROOT]
sh build-tools/build-for-pypi.sh
```

Normal releases are published by the tag workflow. The tag must exactly match
the package version, point to a commit on ``origin/master``, and be pushed only
after the release pull request and ``master`` CI pass:
```bash
git tag -a v3.4.0 -m "labelImg++ 3.4.0"
git push origin v3.4.0
```

The workflow tests Python 3.8 through 3.13, tests the optional SAM dependency
on the oldest and newest supported Python versions, runs plugin discovery,
packaged-wheel, lifecycle, threading, performance, and teardown gates across
Python 3.8 through 3.13, verifies Qt resources, checks the wheel and sdist with
Twine, and waits for all native packaging jobs
before publishing the exact tested distributions through PyPI Trusted
Publishing. Native binaries remain private workflow artifacts.

Publishing must include both ``libs*`` and the stable ``labelimgplusplus*``
public namespace. The base wheel has no plugin-only dependencies and contains
no third-party plugins. The packaged fixture under
``tests/fixtures/plugin_distribution`` is built and installed separately in a
temporary environment so entry-point behavior is tested from real distribution
metadata.

PyInstaller builds contain the plugin host but intentionally bundle no external
plugin distributions. The Linux release job boots the base executable with
``LABELIMGPP_DISABLE_PLUGINS=1`` before upload. Use the normal Python package in
a virtual environment when separately installed plugins are required.

## Build for Ubuntu

```bash
cd build-tools
pip install pyinstaller
sh build-ubuntu-binary.sh
```

## Build for Windows

```bash
cd build-tools
pip install pyinstaller
sh build-windows-binary.sh
```

## Build for macOS

```bash
cd build-tools
./build-for-macos.sh
```

## Prerequisites

- Python 3.8 through 3.13
- PyQt5
- lxml
- pyinstaller (for binary builds)
- build & twine (for PyPI uploads)

```bash
pip install pyinstaller build twine
```
