# Settings reference

labelImg++ stores application and plugin preferences as JSON. It never
deserializes pickle data.

## Location and safety

The default file is:

```text
~/.labelImgSettings.json
```

`libs/core/settings.py` loads the file during MainWindow construction and saves
it on close or when a plugin enablement/configuration change must persist
immediately. Corrupt JSON, invalid UTF-8, and old pickle content are rejected
and defaults are used.

Qt values used by the application are represented by whitelisted `__type__`
tags for `QSize`, `QPoint`, `QColor`, `QByteArray`, and known enums. Plugin
settings cannot use `__type__` at any nesting level, preventing a plugin value
from entering the application's tagged-value decoder.

## Application settings

Common persisted keys include:

| Key | Type | Description |
|---|---|---|
| `filename` | string | Last startup file when no directory is active |
| `recentFiles` | list | Recently opened files/projects |
| `window/size` | tagged QSize | Main window size |
| `window/position` | tagged QPoint | Validated on-screen position |
| `window/state` | tagged QByteArray | Dock and toolbar layout |
| `line/color` | tagged QColor | Default annotation line color |
| `fill/color` | tagged QColor | Default annotation fill color |
| `advanced` | boolean | Advanced mode |
| `galleryMode` | boolean | Full gallery mode |
| `savedir` | string | Annotation destination |
| `lastOpenDir` | string | Last browsed directory |
| `autosave` | boolean | Save while navigating |
| `autoSaveEnabled` | boolean | Timer-based autosave |
| `autoSaveInterval` | integer | Timer interval in seconds |
| `labelFileFormat` | tagged enum | Active built-in annotation format |
| `shortcuts` | object | Built-in and retained plugin shortcut overrides |

See `libs/utils/constants.py` for the complete built-in key list. Existing
annotation formats, filenames, class ordering, and project data are not stored
in the plugin section.

## Plugin settings

Plugin state uses one top-level JSON object:

```json
{
  "plugins": {
    "enabled": ["com.example.review"],
    "config": {
      "com.example.review": {
        "threshold": 0.8
      }
    },
    "metadata": {
      "com.example.review": {
        "display_name": "Example Review",
        "version": "0.1.0",
        "api_major": 1,
        "capabilities": ["commands"],
        "description": "",
        "homepage": "https://example.com/plugin"
      }
    },
    "shortcut_owners": {
      "plugin.com.example.review.run": "com.example.review"
    }
  }
}
```

- `plugins.enabled` is the sorted set requested for the next startup. Newly
  discovered plugins default to disabled. Changes made in **Tools → Plugins…**
  save immediately and require restart.
- `plugins.config.<plugin-id>` is accessible only through that plugin's
  `PluginSettings` service. Values must be strict JSON with string keys, finite
  numbers, no cycles, and no `__type__` key.
- `plugins.metadata.<plugin-id>` caches structurally validated metadata after
  an enabled load so the manager can show API/capability details without
  importing a disabled plugin on later starts.
- `plugins.shortcut_owners` is a host-maintained ownership index used to forget
  retained shortcuts exactly even when one plugin ID is a dot-prefix of
  another. Plugins cannot read or write it through `PluginSettings`.
- Configuration and cached metadata remain when a distribution is removed.
  **Forget Unavailable Plugin** removes them, its enabled state, and retained
  `plugin.<plugin-id>.*` shortcut keys.

Disabled plugin shortcuts remain in `shortcuts` but are hidden from the
shortcut editor and conflict detection until their commands are registered.
Reset/import/export includes active plugin commands; unknown non-plugin keys
are ignored.

## Inspect the file

Use a JSON parser rather than pickle:

```bash
python -m json.tool ~/.labelImgSettings.json
```

Do not edit the file while labelImg++ is running; a later application or
plugin save may replace manual changes.

## Recovery and reset

To bypass plugin discovery/loading without changing settings:

```bash
LABELIMGPP_DISABLE_PLUGINS=1 labelimgpp
```

To reset every application and plugin preference, use **File → Reset All** or
remove the JSON file while the application is closed:

```bash
rm ~/.labelImgSettings.json
```

Reset All keeps the configured settings path usable, relaunches the
application, and does not delete annotations, images, videos, or video project
databases.
