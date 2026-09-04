# labelImgPlusPlus Build Tools

## Deploy to PyPI

```bash
cd [ROOT]
sh build-tools/build-for-pypi.sh
```

Normal releases are published by the tag workflow. The tag must exactly match
the package version, point to a commit already on ``origin/master``, and be
pushed only after the release pull request and ``master`` CI pass:

```bash
git tag -a v4.0.0rc1 -m "labelImg++ 4.0.0rc1"
git push origin v4.0.0rc1
```

The workflow tests Python 3.10 through 3.13, tests SAM and combined SAM/video
on 3.10 and 3.13, runs video tests across the full matrix, and retains the
Windows/macOS video smoke on 3.11. Plugin discovery, packaged-wheel,
lifecycle, threading, performance, and teardown gates also run across
3.10–3.13.

The release job checks wheel and sdist contents, rebuilds a wheel from the
sdist, then verifies packaged assets, base-import isolation, all three console
entry points, and normal startup from clean environments outside the checkout.
It publishes only the original tested wheel and sdist after all Linux, macOS,
and Windows native jobs pass.

## Qualify a release candidate without publishing

Open a pull request into `dev` and apply the exact `release-candidate` label.
The `labeled` event runs the full test, distribution, and Linux, macOS, and
Windows native-package jobs against the pull request's head commit rather than
the synthetic merge commit. The label remains effective for each subsequent
`synchronize` event, so every pushed fix receives a new matching-SHA run.

Candidate runs upload the tested distributions and native executables but
always skip the tag-only PyPI publisher. Do not tag a candidate until the pull
request has passed review, followed the repository's merge process, and the
release commit is present on `origin/master`.

Publishing must include both ``libs*`` and the stable ``labelimgplusplus*``
public namespace. The base wheel has no plugin-only dependencies and contains
no third-party plugins. The packaged fixture under
``tests/fixtures/plugin_distribution`` is built and installed separately in a
temporary environment so entry-point behavior is tested from real distribution
metadata.

PyInstaller builds contain the plugin host but intentionally bundle no external
plugin distributions. All native jobs use
``build-tools/labelImgPlusPlus.spec``, copy the executable outside the checkout,
run ``--verify-assets``, and require normal startup to remain alive before
uploading that exact executable. Use the normal Python package in a virtual
environment when separately installed plugins are required.

## Build for Ubuntu

```bash
python -m pip install -e . pyinstaller
sh build-tools/build-ubuntu-binary.sh
```

The CI release artifact pins ``ubuntu-22.04`` so a newer
``ubuntu-latest`` image cannot silently raise its glibc requirement.

## Build for Windows

```bash
py -m pip install -e . pyinstaller
sh build-tools/build-windows-binary.sh
```

## Build for macOS

```bash
python3 -m pip install -e . pyinstaller
sh build-tools/build-for-macos.sh
```

Each wrapper runs from the repository root with ``QT_API=pyqt6`` and invokes:

```bash
python -m PyInstaller --clean --noconfirm build-tools/labelImgPlusPlus.spec
```

## Prerequisites

- Python 3.10 through 3.13
- PyQt6 6.11
- lxml
- pyinstaller (for binary builds)
- build and twine (for Python distributions)

```bash
python -m pip install -e . pyinstaller build twine
```
