# Settings Reference

labelImg++ persists user preferences using a pickle-based settings system.

**File:** `libs/settings.py` (lines 5-45)

## Settings Location

```
~/.labelImgSettings.pkl
```

The settings file is created automatically on first run and updated when the application closes.

## Settings Class

```python
class Settings(object):
    def __init__(self):
        self.data = {}
        self.path = get_config('.labelImgSettings.pkl')

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def save(self):
        with open(self.path, 'wb') as f:
            pickle.dump(self.data, f)

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, 'rb') as f:
                self.data = pickle.load(f)

    def reset(self):
        if os.path.exists(self.path):
            os.remove(self.path)
```

## Settings Keys

**File:** `libs/constants.py` (lines 1-20)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `SETTING_FILENAME` | str | '' | Last opened file path |
| `SETTING_RECENT_FILES` | list | [] | Recent files list (max 7) |
| `SETTING_WIN_SIZE` | QSize | (600, 500) | Window size |
| `SETTING_WIN_POSE` | QPoint | (0, 0) | Window position |
| `SETTING_WIN_STATE` | QByteArray | - | Dock/toolbar layout |
| `SETTING_LINE_COLOR` | QColor | Green | Default line color |
| `SETTING_FILL_COLOR` | QColor | Red | Default fill color |
| `SETTING_ADVANCE_MODE` | bool | False | Advanced mode enabled |
| `SETTING_AUTO_SAVE` | bool | False | Auto-save on navigate |
| `SETTING_SINGLE_CLASS` | bool | False | Single class mode |
| `SETTING_PAINT_LABEL` | bool | False | Display labels on boxes |
| `SETTING_DRAW_SQUARE` | bool | False | Constrain to squares |
| `SETTING_SAVE_DIR` | str | None | Default save directory |
| `SETTING_LAST_OPEN_DIR` | str | None | Last browsed directory |
| `SETTING_LABEL_FILE_FORMAT` | enum | PASCAL_VOC | Default format |

## Setting Details

### Window State

```python
# Saved on close (labelImgPlusPlus.py:1255-1257)
settings[SETTING_WIN_SIZE] = self.size()
settings[SETTING_WIN_POSE] = self.pos()
settings[SETTING_WIN_STATE] = self.saveState()

# Restored on start (labelImgPlusPlus.py:485-503)
size = settings.get(SETTING_WIN_SIZE, QSize(600, 500))
position = settings.get(SETTING_WIN_POSE, QPoint(0, 0))
self.resize(size)
self.move(position)
self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
```

### Multi-Monitor Handling

```python
# Validates position is on a visible screen
saved_position = settings.get(SETTING_WIN_POSE, position)
for i in range(QApplication.desktop().screenCount()):
    if QApplication.desktop().availableGeometry(i).contains(saved_position):
        position = saved_position
        break
```

### Recent Files

```python
# Maximum 7 recent files
self.max_recent = 7

def add_recent_file(self, file_path):
    if file_path in self.recent_files:
        self.recent_files.remove(file_path)
    elif len(self.recent_files) >= self.max_recent:
        self.recent_files.pop()
    self.recent_files.insert(0, file_path)
```

### Colors

```python
# Default colors (libs/shape.py)
DEFAULT_LINE_COLOR = QColor(0, 255, 0, 128)    # Green, semi-transparent
DEFAULT_FILL_COLOR = QColor(255, 0, 0, 128)    # Red, semi-transparent

# Saved as QColor objects
settings[SETTING_LINE_COLOR] = self.line_color
settings[SETTING_FILL_COLOR] = self.fill_color
```

### Format Setting

```python
# Saved as enum value
settings[SETTING_LABEL_FILE_FORMAT] = self.label_file_format

# Restored
self.label_file_format = settings.get(
    SETTING_LABEL_FILE_FORMAT,
    LabelFileFormat.PASCAL_VOC
)
```

## UI Menu Options

These settings are accessible via the View menu:

| Menu Item | Setting Key | Description |
|-----------|-------------|-------------|
| Auto Save Mode | `SETTING_AUTO_SAVE` | Save when navigating |
| Single Class Mode | `SETTING_SINGLE_CLASS` | Reuse last label |
| Display Labels | `SETTING_PAINT_LABEL` | Show labels on canvas |
| Draw Squares | `SETTING_DRAW_SQUARE` | Square constraint |

## Resetting Settings

### Via Menu

```
File > Reset All
```

This calls `MainWindow.reset_all()`:
```python
def reset_all(self):
    self.settings.reset()  # Deletes settings file
    self.close()
    process = QProcess()
    process.startDetached(os.path.abspath(__file__))  # Restart app
```

### Manual Reset

```bash
rm ~/.labelImgSettings.pkl
```

## Save Triggers

Settings are saved in `closeEvent`:

```python
def closeEvent(self, event):
    if not self.may_continue():
        event.ignore()
        return

    settings = self.settings
    # ... set all values ...
    settings.save()
```

## Load Timing

Settings are loaded during `MainWindow.__init__`:

```python
def __init__(self, ...):
    # Line 81-83
    self.settings = Settings()
    self.settings.load()
    settings = self.settings
```

## Constants Reference

```python
# libs/constants.py
SETTING_FILENAME = 'filename'
SETTING_RECENT_FILES = 'recentFiles'
SETTING_WIN_SIZE = 'window/size'
SETTING_WIN_POSE = 'window/position'
SETTING_WIN_STATE = 'window/state'
SETTING_LINE_COLOR = 'line/color'
SETTING_FILL_COLOR = 'fill/color'
SETTING_ADVANCE_MODE = 'advanced'
SETTING_WIN_GEOMETRY = 'window/geometry'
SETTING_SAVE_DIR = 'savedir'
SETTING_LAST_OPEN_DIR = 'lastOpenDir'
SETTING_AUTO_SAVE = 'autosave'
SETTING_SINGLE_CLASS = 'singleclass'
SETTING_PAINT_LABEL = 'paintlabel'
SETTING_DRAW_SQUARE = 'draw/square'
SETTING_LABEL_FILE_FORMAT = 'labelFileFormat'
```

## Debugging Settings

To inspect current settings:

```python
import pickle
with open(os.path.expanduser('~/.labelImgSettings.pkl'), 'rb') as f:
    data = pickle.load(f)
    for key, value in data.items():
        print(f"{key}: {value}")
```
