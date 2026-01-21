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
|  |  :/strings-zh-CN  (locale specific)               |   |
|  |       |                                            |   |
|  |       v                                            |   |
|  |  :/strings-zh     (language only)                 |   |
|  |       |                                            |   |
|  |       v                                            |   |
|  |  :/strings        (base/English)                  |   |
|  +--------------------------------------------------+   |
|                                                          |
+----------------------------------------------------------+
```

## File Structure

```
resources/
├── strings/
│   ├── strings.properties        # Base (English)
│   ├── strings-zh-CN.properties  # Simplified Chinese
│   ├── strings-zh-TW.properties  # Traditional Chinese
│   └── strings-ja-JP.properties  # Japanese
└── resources.qrc                 # Qt resource file
```

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

Create `resources/strings/strings-XX-YY.properties` where:
- `XX` = language code (e.g., `fr`, `de`, `es`)
- `YY` = country code (optional, e.g., `FR`, `DE`, `ES`)

Example for French: `strings-fr-FR.properties`

### Step 2: Copy and Translate Base File

Start with the base English file:

```bash
cp resources/strings/strings.properties resources/strings/strings-fr-FR.properties
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

### Step 3: Update resources.qrc

Add your file to `resources.qrc`:

```xml
<RCC>
    <qresource prefix="/">
        <!-- ... other resources ... -->
    </qresource>
    <qresource prefix="/strings">
        <file alias="">strings/strings.properties</file>
        <file alias="-zh-CN">strings/strings-zh-CN.properties</file>
        <file alias="-zh-TW">strings/strings-zh-TW.properties</file>
        <file alias="-ja-JP">strings/strings-ja-JP.properties</file>
        <file alias="-fr-FR">strings/strings-fr-FR.properties</file>  <!-- Add -->
    </qresource>
</RCC>
```

### Step 4: Rebuild Resources

```bash
make qt5py3
# Or manually:
pyrcc5 -o libs/resources.py resources.qrc
```

### Step 5: Test

```bash
# Set locale and run
export LANG=fr_FR.UTF-8
python labelImg.py
```

## StringBundle Implementation

**File:** `libs/stringBundle.py` (lines 23-78)

```python
class StringBundle:
    """Loads and provides localized strings."""

    __create_key = object()  # Private key for factory pattern

    def __init__(self, create_key, locale_str):
        assert(create_key == StringBundle.__create_key)
        self.id_to_message = {}
        paths = self.__create_lookup_fallback_list(locale_str)
        for path in paths:
            self.__load_bundle(path)

    @classmethod
    def get_bundle(cls, locale_str=None):
        """Get StringBundle for current or specified locale.

        Args:
            locale_str: Override locale (e.g., 'zh_CN', 'ja_JP')

        Returns:
            StringBundle instance with loaded strings
        """
        if locale_str is None:
            try:
                locale_str = locale.getdefaultlocale()[0]
            except:
                locale_str = 'en'
        return StringBundle(cls.__create_key, locale_str)

    def get_string(self, string_id):
        """Get localized string by ID.

        Args:
            string_id: Key from properties file

        Returns:
            Localized string value

        Raises:
            AssertionError: If string_id not found
        """
        assert(string_id in self.id_to_message), \
            "Missing string id: " + string_id
        return self.id_to_message[string_id]
```

### Fallback Chain Creation

```python
def __create_lookup_fallback_list(self, locale_str):
    """Create list of paths to search, most to least specific.

    Example for 'zh_CN':
        [':/strings', ':/strings-zh', ':/strings-zh-CN']

    Strings are loaded in order, so more specific overrides less.
    """
    result_paths = []
    base_path = ":/strings"
    result_paths.append(base_path)

    if locale_str is not None:
        # Split locale into tags (zh_CN -> ['zh', 'CN'])
        tags = re.split('[^a-zA-Z]', locale_str)
        for tag in tags:
            last_path = result_paths[-1]
            result_paths.append(last_path + '-' + tag)

    return result_paths
```

## Using Strings in Code

### In labelImg.py

```python
# Get the string helper function
from libs.stringBundle import StringBundle

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
from libs.stringBundle import StringBundle

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

Edit `resources/strings/strings.properties`:

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

### Step 3: Rebuild and Test

```bash
make qt5py3
python labelImg.py
```

## Testing Translations

### Test Specific Locale

```bash
# Linux/Mac
export LANG=zh_CN.UTF-8
python labelImg.py

# Or programmatically override
python -c "
from libs.stringBundle import StringBundle
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
base = load_properties('resources/strings/strings.properties')
print(f"Base has {len(base)} keys")

# Check translations
for filename in os.listdir('resources/strings'):
    if filename.startswith('strings-') and filename.endswith('.properties'):
        path = f'resources/strings/{filename}'
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
3. Rebuild resources:
   ```bash
   make qt5py3
   ```

### String Not Found Error

**Cause:** Key missing from properties file.

**Solution:** Add key to `strings.properties` and rebuild.

### Translation Not Applied

**Cause:** Fallback chain not matching locale.

**Debug:**
```python
from libs.stringBundle import StringBundle
import locale
print(f"System locale: {locale.getdefaultlocale()}")

bundle = StringBundle.get_bundle()
print(f"Loaded strings: {len(bundle.id_to_message)}")
```

## Checklist

- [ ] Created `strings-XX-YY.properties` file
- [ ] Translated all keys from base file
- [ ] Updated `resources.qrc` with correct alias
- [ ] Rebuilt resources with `make qt5py3`
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
