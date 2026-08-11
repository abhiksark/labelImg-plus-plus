# libs/__init__.py
"""LabelImg++ library package."""

import importlib

__version__ = '3.4.0'
__version_info__ = tuple(__version__.split('.'))

__all__ = ['core', 'formats', 'utils', 'widgets']


def __getattr__(name):
    """Retain convenient subpackage access without eager Qt imports."""
    if name not in __all__:
        raise AttributeError(name)
    module = importlib.import_module('libs.' + name)
    globals()[name] = module
    return module
