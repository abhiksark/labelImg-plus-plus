# Optional dependencies

The base `labelimgplusplus` install contains image annotation support and does
not import video, SAM, or profiling libraries during startup.

## Candidate, source, and stable installs

These guides describe the **4.0.0rc1 PyQt6 release candidate**. Use Python 3.10
or newer; the supported matrix is 3.10–3.13. The pinned PyPI commands below
select this exact candidate once it is published, rather than the latest
stable package.

Before publication, or when working from candidate source, install from the
repository root in the same virtual environment:

```bash
python -m pip install -e ".[sam,video]"
```

Use `".[sam]"`, `".[video]"`, or `".[video,profile]"` instead when only those
extras are needed. The editable install follows this checkout.

For the latest stable package instead, omit `==4.0.0rc1` in a separate
environment. An extra cannot add candidate features to an older release.
Python 3.8/3.9 users need the older 3.5.x line; the historical 4.0.0rc0
prerelease uses PyQt5, not this candidate's PyQt6.

Candidate requirements are defined in
[`pyproject.toml`](../../pyproject.toml), including its Python-version markers.

## Smart video

```bash
python -m pip install "labelimgplusplus[video]==4.0.0rc1"
```

For the candidate, the extra installs the PyAV line selected by the active
Python version, NumPy, and headless OpenCV: `av>=17.1,<18` on Python 3.10 and
`av>=18,<19` on Python 3.11 or newer. The supported Python matrix currently
ends at 3.13. The accepted local-container matrix is MP4, MOV, MKV, and AVI.
Other containers supported by the installed FFmpeg/PyAV build may work, but
are not part of the compatibility contract.

## SAM and smart video together

```bash
python -m pip install "labelimgplusplus[sam,video]==4.0.0rc1"
```

Both extras resolve to the same `opencv-python-headless>=4.8,<6` distribution.
MobileSAM Smart Select remains a paused-frame Box/Polygon helper in video
documents; it does not run temporal mask propagation. Whole-video propagation
uses portable OpenCV or the separately configured
[SAM 2 backend](../features/smart-video-annotation.md#optional-sam-2-backend).
Torch, torchvision, and SAM 2 are not included in these extras; SAM 2 requires
its own source installation, compatible CUDA runtime, checkpoint, and config.

## Profiling tools

```bash
python -m pip install "labelimgplusplus[video,profile]==4.0.0rc1"
```

This adds process metrics and native sampling tools used by the local
workstation gates. See [Local performance profiling](../performance.md).

Packaged base executables intentionally remain optional-feature-free. Install
the Python package with the desired extra to use smart video or SAM.
