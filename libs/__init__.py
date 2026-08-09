# libs/__init__.py
"""LabelImg++ library package."""

__version__ = '3.0.0rc0'
__version_info__ = tuple(__version__.split('.'))

# Re-export subpackages for convenient access
from libs import core, formats, widgets, utils
