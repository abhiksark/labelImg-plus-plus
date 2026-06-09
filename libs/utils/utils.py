from math import hypot, sqrt
from libs.utils.ustr import ustr
import hashlib
import re
import sys

try:
    from PyQt5.QtGui import QIcon, QColor, QPainter, QPixmap
    from PyQt5.QtCore import QRegExp, QSize
    from PyQt5.QtWidgets import QPushButton, QAction, QMenu, QWidget
    QT5 = True
except ImportError:
    from PyQt4.QtGui import QIcon, QColor, QPushButton, QAction, QMenu, QWidget, QRegExpValidator
    from PyQt4.QtCore import QRegExp
    QT5 = False

# QRegExpValidator location differs between Qt versions
if QT5:
    from PyQt5.QtGui import QRegExpValidator
else:
    pass  # Already imported above for PyQt4


def new_icon(icon):
    return QIcon(':/' + icon)


def themed_icon(icon_name, theme):
    """Create a theme-aware icon, recoloring dark pixels for dark mode.

    Uses QPainter CompositionMode_SourceIn to replace all opaque pixels
    with the theme's text color while preserving alpha transparency.

    Args:
        icon_name: Icon resource name (e.g., 'format_yolo').
        theme: Theme enum value from libs.utils.styles.

    Returns:
        QIcon recolored for the given theme.
    """
    from libs.utils.styles import Theme, get_theme_colors, hex_to_qcolor

    base_icon = QIcon(':/' + icon_name)
    if theme == Theme.LIGHT:
        return base_icon

    text_color = hex_to_qcolor(get_theme_colors(theme)['text'])

    # Resource-loaded icons often report empty availableSizes(),
    # so request a reasonable default size to get the actual pixmap.
    pixmap = base_icon.pixmap(QSize(128, 128))
    if pixmap.isNull():
        return base_icon

    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), text_color)
    painter.end()

    recolored = QIcon()
    recolored.addPixmap(pixmap)
    return recolored


def new_button(text, icon=None, slot=None):
    b = QPushButton(text)
    if icon is not None:
        b.setIcon(new_icon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


def new_action(parent, text, slot=None, shortcut=None, icon=None,
               tip=None, checkable=False, enabled=True):
    """Create a new action and assign callbacks, shortcuts, etc."""
    a = QAction(text, parent)
    if icon is not None:
        a.setIcon(new_icon(icon))
    if shortcut is not None:
        if isinstance(shortcut, (list, tuple)):
            a.setShortcuts(shortcut)
        else:
            a.setShortcut(shortcut)
    if tip is not None:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot is not None:
        a.triggered.connect(slot)
    if checkable:
        a.setCheckable(True)
    a.setEnabled(enabled)
    return a


def add_actions(widget, actions):
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QMenu):
            widget.addMenu(action)
        elif isinstance(action, QWidget):
            widget.addWidget(action)
        else:
            widget.addAction(action)


def label_validator():
    return QRegExpValidator(QRegExp(r'^[^ \t].+'), None)


class Struct(object):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())


def format_shortcut(text):
    mod, key = text.split('+', 1)
    return '<b>%s</b>+<b>%s</b>' % (mod, key)


def generate_color_by_text(text):
    s = ustr(text)
    hash_code = int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16)
    r = int((hash_code / 255) % 255)
    g = int((hash_code / 65025) % 255)
    b = int((hash_code / 16581375) % 255)
    return QColor(r, g, b, 100)


def have_qstring():
    """py3/qt5 have no QString wrapper; py3 has a native unicode str type."""
    return False


def util_qt_strlistclass():
    return list


def natural_sort(list, key=lambda s:s):
    """
    Sort the list into natural alphanumeric order.
    """
    def get_alphanum_key_func(key):
        convert = lambda text: int(text) if text.isdigit() else text
        return lambda s: [convert(c) for c in re.split('([0-9]+)', key(s))]
    sort_key = get_alphanum_key_func(key)
    list.sort(key=sort_key)


# QT4 has a trimmed method, in QT5 this is called strip
if QT5:
    def trimmed(text):
        return text.strip()
else:
    def trimmed(text):
        return text.trimmed()


def _perpendicular_distance(point, line_start, line_end):
    """Calculate perpendicular distance from point to line segment."""
    dx = line_end.x() - line_start.x()
    dy = line_end.y() - line_start.y()
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return hypot(point.x() - line_start.x(), point.y() - line_start.y())
    t = max(0, min(1, ((point.x() - line_start.x()) * dx +
                       (point.y() - line_start.y()) * dy) / length_sq))
    proj_x = line_start.x() + t * dx
    proj_y = line_start.y() + t * dy
    return hypot(point.x() - proj_x, point.y() - proj_y)


def douglas_peucker(points, epsilon):
    """Simplify a polyline using Douglas-Peucker algorithm."""
    if len(points) <= 2:
        return points
    max_dist = 0
    max_index = 0
    for i in range(1, len(points) - 1):
        d = _perpendicular_distance(points[i], points[0], points[-1])
        if d > max_dist:
            max_dist = d
            max_index = i
    if max_dist > epsilon:
        left = douglas_peucker(points[:max_index + 1], epsilon)
        right = douglas_peucker(points[max_index:], epsilon)
        return left[:-1] + right
    return [points[0], points[-1]]
