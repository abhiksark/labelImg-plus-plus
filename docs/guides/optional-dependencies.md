# Optional dependencies

The base `labelimgplusplus` install contains image annotation support and does
not import video, SAM, or profiling libraries during startup.

## Smart video

```bash
pip install "labelimgplusplus[video]"
```

The extra installs the PyAV line supported by the active Python version,
NumPy, and headless OpenCV. Python 3.10 uses PyAV 17; Python 3.11 through 3.13
use PyAV 18. labelImg++ 4.0 requires Python 3.10 or newer; Python 3.8 and 3.9
users must remain on stable 3.5.x. The accepted local-container matrix is MP4,
MOV, MKV, and AVI. Other containers
supported by the installed FFmpeg/PyAV build may work, but are not part of the
compatibility contract.

## SAM and smart video together

```bash
pip install "labelimgplusplus[sam,video]"
```

Both extras resolve to the same `opencv-python-headless>=4.8,<6` distribution.
SAM remains a paused-frame polygon helper in video documents; it does not run
temporal mask propagation.

## Profiling tools

```bash
pip install "labelimgplusplus[video,profile]"
```

This adds process metrics and native sampling tools used by the local
workstation gates. See [Local performance profiling](../performance.md).

Packaged base executables intentionally remain optional-feature-free. Install
the Python package with the desired extra to use smart video or SAM.
