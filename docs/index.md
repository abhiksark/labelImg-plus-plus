# labelImg++ Developer Documentation

This documentation provides comprehensive guidance for developers working with the labelImg++ image annotation tool.

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Architecture Overview](architecture.md) | High-level system design and data flow |
| [Components](components/) | Deep dives into core classes |
| [Annotation Formats](formats/) | Format specifications and I/O |
| [Extension Guides](guides/) | How to extend labelImg++ |
| [Reference](reference/) | Shortcuts, settings, troubleshooting |

## Project Structure

```
labelImg++/
├── labelImgPlusPlus.py              # Entry point, MainWindow class
├── libs/
│   ├── canvas.py            # Drawing surface widget
│   ├── shape.py             # Annotation shape representation
│   ├── labelFile.py         # Format orchestration
│   ├── pascal_voc_io.py     # PASCAL VOC XML format I/O
│   ├── yolo_io.py           # YOLO text format I/O
│   ├── create_ml_io.py      # CreateML JSON format I/O
│   ├── settings.py          # User preferences persistence
│   ├── stringBundle.py      # Internationalization (i18n)
│   ├── labelDialog.py       # Label input dialog
│   ├── colorDialog.py       # Color picker dialog
│   ├── zoomWidget.py        # Zoom control widget
│   ├── lightWidget.py       # Brightness control widget
│   ├── toolBar.py           # Custom toolbar
│   ├── combobox.py          # Label filter combobox
│   ├── utils.py             # Utility functions
│   ├── constants.py         # Application constants
│   └── ustr.py              # Unicode string utilities
├── resources/
│   ├── icons/               # Application icons
│   └── strings/             # Localization files
│       ├── strings.properties        # English (default)
│       ├── strings-zh-CN.properties  # Simplified Chinese
│       ├── strings-zh-TW.properties  # Traditional Chinese
│       └── strings-ja-JP.properties  # Japanese
├── data/
│   └── predefined_classes.txt   # Default class labels
└── tests/                   # Unit tests
```

## Component Overview

```
+------------------------------------------------------------------+
|                         MainWindow                                |
|  +------------------+  +------------------+  +------------------+ |
|  |    Menu Bar     |  |    Tool Bar      |  |   Status Bar     | |
|  +------------------+  +------------------+  +------------------+ |
|  +-------------------------------+  +---------------------------+ |
|  |         QScrollArea           |  |     Dock Widgets          | |
|  |  +-----------------------+    |  |  +---------------------+  | |
|  |  |                       |    |  |  |   Label List        |  | |
|  |  |       Canvas          |    |  |  |   (annotations)     |  | |
|  |  |   +-------------+     |    |  |  +---------------------+  | |
|  |  |   |   Shapes    |     |    |  |  +---------------------+  | |
|  |  |   +-------------+     |    |  |  |   File List         |  | |
|  |  |                       |    |  |  |   (images)          |  | |
|  |  +-----------------------+    |  |  +---------------------+  | |
|  +-------------------------------+  +---------------------------+ |
+------------------------------------------------------------------+
```

## Development Setup

### Prerequisites
- Python 3.6+
- PyQt5
- lxml

### Installation

```bash
# Install dependencies
pip3 install -r requirements/requirements-linux-python3.txt

# Build Qt resources (required before first run)
make qt5py3

# Run the application
python3 labelImgPlusPlus.py
```

### Running Tests

```bash
# Run all tests
make test

# Run specific test file
python3 -m unittest tests.test_io

# Run with verbose output
python3 -m unittest discover tests -v
```

## Key Concepts

### Annotation Workflow
1. User opens image or directory
2. Canvas displays image with existing annotations (if any)
3. User draws bounding boxes (CREATE mode) or edits existing (EDIT mode)
4. Label dialog prompts for class label
5. Annotations saved in selected format (PASCAL VOC, YOLO, or CreateML)

### Coordinate Systems
- **Screen coordinates**: Widget pixel positions
- **Image coordinates**: Actual image pixel positions
- Transformation handled by `Canvas.transform_pos()`

### Supported Formats

| Format | Extension | Coordinate Type |
|--------|-----------|-----------------|
| PASCAL VOC | .xml | Corner-based (xmin, ymin, xmax, ymax) |
| YOLO | .txt | Normalized center (x_center, y_center, w, h) |
| CreateML | .json | Pixel center (x, y, width, height) |

## Documentation Index

### Core Components
- [Architecture Overview](architecture.md) - System design and patterns
- [MainWindow](components/mainwindow.md) - UI orchestration and state management
- [Canvas](components/canvas.md) - Drawing and interaction
- [Shape](components/shape.md) - Annotation representation
- [LabelFile](components/label-file.md) - Format coordination

### Annotation Formats
- [Formats Overview](formats/overview.md) - Comparison and selection
- [PASCAL VOC](formats/pascal-voc.md) - XML format details
- [YOLO](formats/yolo.md) - Text format details
- [CreateML](formats/createml.md) - JSON format details

### Guides
- [Extension Guide](guides/extension-guide.md) - Overview of extension points
- [Adding Formats](guides/adding-formats.md) - Create new annotation formats
- [Adding Features](guides/adding-features.md) - Add new actions and UI
- [i18n Guide](guides/i18n-guide.md) - Add new languages
- [Testing Plan](testing-plan.md) - Test audit findings and roadmap

### Reference
- [Keyboard Shortcuts](reference/keyboard-shortcuts.md) - Complete hotkey reference
- [Settings](reference/settings.md) - Configuration options
- [Troubleshooting](reference/troubleshooting.md) - Common issues and solutions
