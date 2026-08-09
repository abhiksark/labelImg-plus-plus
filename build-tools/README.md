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
git tag -a v3.0.0 -m "labelImg++ 3.0.0"
git push origin v3.0.0
```

The workflow tests Python 3.8 through 3.13, tests the optional SAM dependency
on the oldest and newest supported Python versions, verifies Qt resources,
checks the wheel and sdist with Twine, and waits for all native packaging jobs
before publishing the exact tested distributions through PyPI Trusted
Publishing. Native binaries remain private workflow artifacts.

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
