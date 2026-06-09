# libs/integrations/__init__.py
"""Optional, heavy-dependency integrations (SAM).

Importing this package is cheap; its submodules pull torch/cv2/numpy at their
own module load, so they must only be imported on demand (never at app startup)."""
