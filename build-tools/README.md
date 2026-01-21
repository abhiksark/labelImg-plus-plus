# labelImgPlusPlus Build Tools

## Deploy to PyPI

```bash
cd [ROOT]
sh build-tools/build-for-pypi.sh
```

Or use the CI/CD pipeline by tagging a release:
```bash
git tag v2.0.1
git push origin v2.0.1
```

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

- Python 3.6+
- PyQt5
- lxml
- pyinstaller (for binary builds)
- build & twine (for PyPI uploads)

```bash
pip install pyinstaller build twine
```
