# libs/__init__.py
"""LabelImg++ library package."""

__version_info__ = ('2', '0', '0a')
__version__ = '.'.join(__version_info__)  # 2.0.0a

# Re-export subpackages for convenient access
from libs import core, formats, widgets, utils
