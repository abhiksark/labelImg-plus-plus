# libs/__init__.py
"""LabelImg++ library package."""

__version__ = '3.1.0'
__version_info__ = tuple(__version__.split('.'))

# Re-export subpackages for convenient access
from libs import core as core
from libs import formats as formats
from libs import utils as utils
from libs import widgets as widgets
