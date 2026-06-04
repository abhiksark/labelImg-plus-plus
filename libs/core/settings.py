# libs/core/settings.py
import json
import os
from enum import Enum

from PyQt5.QtCore import QByteArray, QPoint, QSize
from PyQt5.QtGui import QColor

# Settings are persisted as JSON rather than pickle: pickle.load executes
# arbitrary code embedded in the file, and ~/.labelImgSettings is a
# user-writable path loaded at every startup (a local code-execution vector).
# JSON cannot describe Qt value types, so the handful that we store are encoded
# as tagged dicts and reconstructed on load.

_TYPE_TAG = '__type__'


def _enum_classes():
    """Whitelist of enum classes allowed during decode.

    Resolved lazily to avoid an import-time core->formats dependency and to
    keep an untrusted settings file from naming arbitrary classes to import.
    """
    from libs.formats.labelFile import LabelFileFormat
    return {'LabelFileFormat': LabelFileFormat}


def _encode(obj):
    """json.dump ``default`` hook: serialize the Qt/enum values we persist."""
    if isinstance(obj, QSize):
        return {_TYPE_TAG: 'QSize', 'w': obj.width(), 'h': obj.height()}
    if isinstance(obj, QPoint):
        return {_TYPE_TAG: 'QPoint', 'x': obj.x(), 'y': obj.y()}
    if isinstance(obj, QColor):
        return {_TYPE_TAG: 'QColor',
                'rgba': [obj.red(), obj.green(), obj.blue(), obj.alpha()]}
    if isinstance(obj, QByteArray):
        return {_TYPE_TAG: 'QByteArray',
                'b64': bytes(obj.toBase64()).decode('ascii')}
    if isinstance(obj, Enum):
        return {_TYPE_TAG: 'Enum', 'cls': type(obj).__name__, 'value': obj.value}
    raise TypeError('Object of type %s is not JSON serializable'
                    % type(obj).__name__)


def _decode(dct):
    """json.load ``object_hook``: rebuild tagged Qt/enum values."""
    tag = dct.get(_TYPE_TAG)
    if tag is None:
        return dct
    if tag == 'QSize':
        return QSize(dct['w'], dct['h'])
    if tag == 'QPoint':
        return QPoint(dct['x'], dct['y'])
    if tag == 'QColor':
        r, g, b, a = dct['rgba']
        return QColor(r, g, b, a)
    if tag == 'QByteArray':
        return QByteArray.fromBase64(dct['b64'].encode('ascii'))
    if tag == 'Enum':
        cls = _enum_classes().get(dct.get('cls'))
        if cls is not None:
            try:
                return cls(dct['value'])
            except ValueError:
                return None
        return dct.get('value')
    return dct


class Settings(object):
    def __init__(self):
        # By default, the home will be in the same folder as labelImg
        home = os.path.expanduser("~")
        self.data = {}
        self.path = os.path.join(home, '.labelImgSettings.json')

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        return default

    def save(self):
        if self.path:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, default=_encode, ensure_ascii=False)
                return True
        return False

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f, object_hook=_decode)
                    return True
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            # Covers a corrupt JSON file as well as a legacy pickle file left
            # over from older versions (its binary bytes are not valid UTF-8
            # JSON, so it is rejected here and never deserialized/executed).
            print(f'Settings file corrupted or legacy, using defaults: {e}')
            self.data = {}
        except OSError as e:
            print(f'Could not read settings file: {e}')
        except Exception as e:
            print(f'Unexpected error loading settings: {e}')
        return False

    def reset(self):
        if self.path and os.path.exists(self.path):
            os.remove(self.path)
            print('Removed settings file {0}'.format(self.path))
        self.data = {}
        # Keep self.path so settings can still be persisted after a reset.
