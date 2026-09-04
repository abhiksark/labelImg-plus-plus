# Internationalization Guide

How to add new language translations to labelImg++.

## Overview

labelImg++ uses a properties file-based internationalization system with locale-based fallback.

```
+----------------------------------------------------------+
|                  i18n Architecture                        |
+----------------------------------------------------------+
|                                                          |
|  System Locale                                           |
|       |                                                  |
|       v                                                  |
|  +----------------+                                      |
|  | StringBundle   |                                      |
|  | .get_bundle()  |                                      |
|  +----------------+                                      |
|       |                                                  |
|       | Creates fallback chain                           |
|       v                                                  |
|  +--------------------------------------------------+   |
|  |  Fallback Chain (most to least specific)          |   |
|  |                                                    |   |
|  |  strings-zh-CN.properties (locale specific)         |   |
|  |       |                                            |   |
|  |       v                                            |   |
|  |  strings-zh.properties    (language only)           |   |
|  |       |                                            |   |
|  |       v                                            |   |
|  |  strings.properties       (base/English)            |   |
|  +--------------------------------------------------+   |
|                                                          |
+----------------------------------------------------------+
```

## File Structure

```
libs/assets/strings/
├── strings.properties        # Base (English)
├── strings-zh-CN.properties  # Simplified Chinese
├── strings-zh-TW.properties  # Traditional Chinese
└── strings-ja-JP.properties  # Japanese
```

The files are UTF-8 package data listed explicitly in `STRING_FILES` in
`libs/utils/assets.py`.

## String File Format

Properties files use simple `key=value` format:

```properties
# Base file: strings.properties
openFile=Open
openFileDetail=Open image or label file
save=Save
saveDetail=Save the labels to a file
quit=Quit
quitApp=Quit application
```

### Rules

1. One key-value pair per line
2. Key and value separated by `=`
3. No quotes needed around values
4. UTF-8 encoding
5. Comments start with `#`
6. Empty lines ignored

## Adding a New Language

### Step 1: Create Properties File

Create `libs/assets/strings/strings-XX-YY.properties` where:
- `XX` = language code (e.g., `fr`, `de`, `es`)
- `YY` = country code (optional, e.g., `FR`, `DE`, `ES`)

Example for French: `strings-fr-FR.properties`

### Step 2: Copy and Translate Base File

Start with the base English file:

```bash
cp libs/assets/strings/strings.properties libs/assets/strings/strings-fr-FR.properties
```

Translate each value:

```properties
# French translations: strings-fr-FR.properties
openFile=Ouvrir
openFileDetail=Ouvrir une image ou un fichier d'annotation
save=Enregistrer
saveDetail=Enregistrer les annotations dans un fichier
quit=Quitter
quitApp=Quitter l'application
nextImg=Image suivante
prevImg=Image précédente
crtBox=Créer un rectangle
delBox=Supprimer le rectangle
```

### Step 3: Add the Bundle to the Catalog

Add the semantic bundle name and relative filename to `STRING_FILES` in
`libs/utils/assets.py`. Locale lookup loads `strings` first, then an available
language bundle, then the available language-territory bundle. Later files
override the same key from earlier files.

### Step 4: Verify Packaged Assets

```bash
python3 labelImgPlusPlus.py --verify-assets
```

There is no RCC compilation step. Source checkouts, wheels, and frozen
applications all read the same UTF-8 files.

### Step 5: Test the Locale

```bash
# Set locale and run
export LANG=fr_FR.UTF-8
labelimgpp  # or: python labelImgPlusPlus.py from source
```

## StringBundle Implementation

**File:** `libs/utils/stringBundle.py`

`StringBundle.get_bundle()` reads package data through
`libs.utils.assets.read_string_bundle()`. It always requires the base
`strings.properties` file and treats missing locale-specific bundles as a
normal fallback:

```python
class StringBundle:
    @classmethod
    def get_bundle(cls, locale_str=None):
        if locale_str is None:
            locale_str = locale.getlocale()[0] or os.getenv('LANG')
        return cls(cls.__create_key, locale_str)

    def __create_lookup_fallback_list(self, locale_str):
        bundle_names = ['strings']
        # zh_CN -> strings, strings-zh, strings-zh-CN
        tags = [
            tag for tag in re.split('[^a-zA-Z]', locale_str or '') if tag
        ][:2]
        if tags:
            bundle_names.append('strings-' + tags[0])
        if len(tags) > 1:
            bundle_names.append('strings-' + tags[0] + '-' + tags[1])
        return bundle_names

    def __load_bundle(self, bundle_name, required=False):
        contents = read_string_bundle(bundle_name, required=required)
        if contents is None:
            return
        for line in contents.splitlines():
            key_value = line.split('=', 1)
            key = key_value[0].strip()
            value = (key_value[1] if len(key_value) > 1 else '').strip()
            self.id_to_message[key] = value.strip('\"')
```

Splitting only at the first `=` preserves values containing `=`. Decoding is
always UTF-8.

## Using Strings in Code

### In labelImgPlusPlus.py

```python
# Get the string helper function
from libs.utils.stringBundle import StringBundle

string_bundle = StringBundle.get_bundle()
get_str = string_bundle.get_string

# Use in code
my_action = action(
    get_str('myFeature'),       # Gets translated text
    self.my_handler,
    'Ctrl+M',
    'icon',
    get_str('myFeatureDetail')  # Gets translated tooltip
)
```

### In Other Files

```python
from libs.utils.stringBundle import StringBundle

def my_function():
    bundle = StringBundle.get_bundle()
    message = bundle.get_string('myMessage')
    print(message)
```

## Complete String Reference

Current strings in `strings.properties`:

| Key | Usage | Category |
|-----|-------|----------|
| `openFile` | Open File action | File |
| `openFileDetail` | Open File tooltip | File |
| `openDir` | Open Directory action | File |
| `save` | Save action | File |
| `saveDetail` | Save tooltip | File |
| `saveAs` | Save As action | File |
| `changeSaveDir` | Change Save Dir action | File |
| `quit` | Quit action | File |
| `quitApp` | Quit tooltip | File |
| `nextImg` | Next Image action | Navigation |
| `prevImg` | Previous Image action | Navigation |
| `verifyImg` | Verify Image action | Navigation |
| `crtBox` | Create RectBox action | Edit |
| `delBox` | Delete RectBox action | Edit |
| `dupBox` | Duplicate RectBox action | Edit |
| `editLabel` | Edit Label action | Edit |
| `zoomin` | Zoom In action | View |
| `zoomout` | Zoom Out action | View |
| `fitWin` | Fit Window action | View |
| `showAllBox` | Show All boxes action | View |
| `hideAllBox` | Hide All boxes action | View |
| `displayLabel` | Display Labels toggle | View |
| `autoSaveMode` | Auto Save Mode toggle | View |
| `singleClsMode` | Single Class Mode toggle | View |
| `advancedMode` | Advanced Mode toggle | View |
| `menu_file` | File menu label | Menu |
| `menu_edit` | Edit menu label | Menu |
| `menu_view` | View menu label | Menu |
| `menu_help` | Help menu label | Menu |
| `boxLabelText` | Label dock title | UI |
| `fileList` | File list dock title | UI |

## Adding New Strings

### Step 1: Add to Base File

Edit `libs/assets/strings/strings.properties`:

```properties
# Add new strings at the end or in appropriate section
myNewFeature=My New Feature
myNewFeatureDetail=Description of my new feature
```

### Step 2: Add to All Translation Files

Edit each `strings-XX-YY.properties` file:

```properties
# strings-zh-CN.properties
myNewFeature=我的新功能
myNewFeatureDetail=我的新功能描述

# strings-ja-JP.properties
myNewFeature=新機能
myNewFeatureDetail=新機能の説明
```

### Step 3: Verify and Test

```bash
python3 labelImgPlusPlus.py --verify-assets
labelimgpp
```

## Testing Translations

### Test Specific Locale

```bash
# Linux/Mac
export LANG=zh_CN.UTF-8
python labelImgPlusPlus.py

# Or programmatically override
python -c "
from libs.utils.stringBundle import StringBundle
bundle = StringBundle.get_bundle('zh_CN')
print(bundle.get_string('openFile'))  # Should print Chinese
"
```

### Verify All Keys Present

```python
# verify_translations.py
import os

def load_properties(path):
    props = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                props[key.strip()] = value.strip()
    return props

# Load base
base = load_properties('libs/assets/strings/strings.properties')
print(f"Base has {len(base)} keys")

# Check translations
for filename in os.listdir('libs/assets/strings'):
    if filename.startswith('strings-') and filename.endswith('.properties'):
        path = f'libs/assets/strings/{filename}'
        trans = load_properties(path)

        missing = set(base.keys()) - set(trans.keys())
        extra = set(trans.keys()) - set(base.keys())

        print(f"\n{filename}:")
        print(f"  Keys: {len(trans)}")
        if missing:
            print(f"  Missing: {missing}")
        if extra:
            print(f"  Extra: {extra}")
```

## Troubleshooting

### Characters Display Incorrectly

**Cause:** Encoding issue or missing font.

**Solutions:**
1. Ensure file is UTF-8 encoded
2. Set system locale:
   ```bash
   export LANG=zh_CN.UTF-8
   ```
3. Validate the asset catalog and relaunch:
   ```bash
   python3 labelImgPlusPlus.py --verify-assets
   ```

### String Not Found Error

**Cause:** Key missing from properties file.

**Solution:** Add the key to `strings.properties`; no compilation is required.

### Translation Not Applied

**Cause:** Fallback chain not matching locale.

**Debug:**
```python
from libs.utils.stringBundle import StringBundle
import locale
print(f"System locale: {locale.getdefaultlocale()}")

bundle = StringBundle.get_bundle()
print(f"Loaded strings: {len(bundle.id_to_message)}")
```

## Checklist

- [ ] Created `strings-XX-YY.properties` file
- [ ] Translated all keys from base file
- [ ] Added the bundle to `STRING_FILES`
- [ ] Passed `python3 labelImgPlusPlus.py --verify-assets`
- [ ] Tested with target locale
- [ ] Verified no missing keys
- [ ] Checked character display

## Supported Locales

| Locale | File | Language |
|--------|------|----------|
| Default | strings.properties | English |
| zh_CN | strings-zh-CN.properties | Simplified Chinese |
| zh_TW | strings-zh-TW.properties | Traditional Chinese |
| ja_JP | strings-ja-JP.properties | Japanese |
