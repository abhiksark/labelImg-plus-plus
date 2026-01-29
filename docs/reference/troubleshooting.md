# Troubleshooting Guide

Common issues and solutions when using labelImg++.

## Application Startup Issues

### Application Won't Start

**Symptoms:**
- Error message on startup
- Window doesn't appear
- Crashes immediately

**Solutions:**

1. **Check PyQt5 Installation**
   ```bash
   python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5 OK')"
   ```

2. **Check lxml Installation**
   ```bash
   python3 -c "from lxml import etree; print('lxml OK')"
   ```

3. **Reset Settings**
   ```bash
   rm ~/.labelImgSettings.pkl
   ```

4. **Rebuild Resources**
   ```bash
   make qt5py3
   # Or manually:
   pyrcc5 -o libs/resources.py resources.qrc
   ```

### ImportError: No module named 'libs.resources'

**Cause:** Qt resources not compiled.

**Solution:**
```bash
make qt5py3
```

### Window Opens Off-Screen

**Cause:** Settings saved with different monitor setup.

**Solution:**
```bash
rm ~/.labelImgSettings.pkl
```

## File Operations

### Annotations Not Saving

**Symptoms:**
- Click save but no file appears
- Status bar shows "Saved to..." but file doesn't exist

**Solutions:**

1. **Check Save Directory**
   - File > Change Save Dir
   - Verify the directory exists and is writable

2. **Check File Permissions**
   ```bash
   ls -la /path/to/save/directory
   ```

3. **Verify Format Selection**
   - Check toolbar format indicator
   - VOC creates .xml, YOLO creates .txt, CreateML creates .json

### Annotations Not Loading

**Symptoms:**
- Open image but existing annotations don't appear
- Canvas shows image without boxes

**Solutions:**

1. **Check Annotation Location**
   - Annotations should be in same directory as image
   - Or set save directory to annotation folder

2. **Check Format Match**
   - VOC expects `image.xml`
   - YOLO expects `image.txt` + `classes.txt`
   - CreateML expects `annotations.json`

3. **Check File Names**
   - Annotation filename must match image filename (different extension)
   - `photo.jpg` needs `photo.xml` or `photo.txt`

### "Error opening file" Dialog

**Causes:**
- Corrupted annotation file
- Invalid XML/JSON/TXT syntax
- Wrong file format

**Solutions:**

1. **Validate XML (PASCAL VOC)**
   ```bash
   xmllint --noout annotation.xml
   ```

2. **Validate JSON (CreateML)**
   ```bash
   python3 -c "import json; json.load(open('annotations.json'))"
   ```

3. **Check YOLO Format**
   - Each line: 5 space-separated values
   - Values should be floats between 0 and 1

## YOLO Format Issues

### Wrong Class Labels

**Cause:** `classes.txt` out of sync with annotations.

**Solutions:**

1. Use `data/predefined_classes.txt` for consistent ordering
2. Don't manually edit `classes.txt` between annotations
3. Start fresh: delete all .txt files and re-annotate

### Classes.txt Not Found

**Symptoms:**
- Error loading YOLO annotations
- "FileNotFoundError: classes.txt"

**Solution:**
- Ensure `classes.txt` is in the same directory as .txt annotations
- Create it manually with class names, one per line

### Coordinates Seem Wrong

**Cause:** YOLO uses normalized coordinates (0-1 range).

**Note:** Coordinates like `0.5 0.5 0.1 0.2` are correct YOLO format.

## Display Issues

### Labels Not Showing on Boxes

**Cause:** Display labels option disabled.

**Solutions:**
1. View > Display Labels (Ctrl+Shift+P)
2. Or check settings: `SETTING_PAINT_LABEL`

### Bounding Boxes Not Visible

**Solutions:**

1. **Check Visibility**
   - View > Show All (Ctrl+A)
   - Check checkboxes in label list

2. **Check Colors**
   - Boxes may match background color
   - Edit > Box Line Color (Ctrl+L)

3. **Check Zoom**
   - Zoom out to see if boxes are off-screen
   - Ctrl+F to fit window

### Chinese/Japanese Characters Garbled

**Cause:** Locale or font issues.

**Solutions:**

1. **Check System Locale**
   ```bash
   echo $LANG
   ```

2. **Set Locale**
   ```bash
   export LANG=zh_CN.UTF-8  # or ja_JP.UTF-8
   ```

3. **Rebuild Resources**
   ```bash
   make qt5py3
   ```

## Performance Issues

### Slow with Large Images

**Cause:** High-resolution images take longer to process.

**Solutions:**

1. Resize images before annotation
2. Use fit-to-window mode (Ctrl+F)
3. Close other applications

### Lag When Drawing

**Cause:** Many annotations on single image.

**Solution:** Split complex scenes into multiple images if possible.

## Data Loss Prevention

### Unsaved Changes Warning

When this dialog appears:
- **Yes**: Save and proceed
- **No**: Discard changes and proceed
- **Cancel**: Stay on current image

### Auto-Save Mode

Enable to prevent accidental loss:
- View > Auto Save Mode
- Saves automatically when navigating images

### Backup Strategy

```bash
# Backup annotations before batch operations
cp -r annotations/ annotations_backup/
```

## Format Conversion Issues

### Converting Between Formats

labelImg++ doesn't convert existing files automatically.

**Manual Workflow:**
1. Load annotations in original format
2. Change format (Ctrl+Y)
3. Save (Ctrl+S) - creates new file in new format
4. Original file remains unchanged

### Lost Information When Converting

| Original | To | Lost Data |
|----------|-----|-----------|
| VOC | YOLO | difficult flag |
| VOC | CreateML | difficult flag |
| YOLO | VOC | precision (rounding) |
| YOLO | CreateML | precision (rounding) |

## Debug Mode

For detailed troubleshooting, add logging:

```python
# Add to labelImgPlusPlus.py after imports
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Getting Help

1. **Check GitHub Issues**
   https://github.com/abhiksark/labelImg-plus-plus/issues

2. **Search Closed Issues**
   Many common problems have solutions in closed issues

3. **Open New Issue**
   Include:
   - Operating system
   - Python version
   - PyQt5 version
   - Error message/traceback
   - Steps to reproduce

## Quick Fixes Summary

| Problem | Quick Fix |
|---------|-----------|
| Won't start | `rm ~/.labelImgSettings.pkl` |
| No resources | `make qt5py3` |
| No save | Check File > Change Save Dir |
| No load | Check annotation filename matches |
| Wrong YOLO classes | Use predefined_classes.txt |
| Boxes invisible | View > Show All (Ctrl+A) |
| Labels not shown | View > Display Labels |
