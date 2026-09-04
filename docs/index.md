# labelImg++ Developer Documentation

This documentation provides comprehensive guidance for developers working with the labelImg++ image annotation tool.

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Architecture Overview](architecture.md) | High-level system design and data flow |
| [Components](components/) | Deep dives into core classes |
| [Annotation Formats](formats/) | Format specifications and I/O |
| [Ultralytics Dataset Export](features/ultralytics-export.md) | Direct YOLO detection layout, splits, and class mapping |
| [Smart Video Annotation](features/smart-video-annotation.md) | PTS-based video projects, tracking, review, and export |
| [Plugin Authoring](guides/plugin-authoring.md) | Build separately installed command plugins |
| [Plugin API Major 1](reference/plugin-api-v1.md) | Stable types, services, lifecycle, and compatibility |
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
- Python 3.10+
- PyQt6 6.11
- lxml

### Installation

```bash
# Install the project and its declared runtime dependencies
python3 -m pip install -e .

# Icons, translations, and licenses are packaged data; no RCC build is needed.
python3 labelImgPlusPlus.py
```

### Running Tests

```bash
# Run the complete suite
make test

# Run a specific test file
QT_QPA_PLATFORM=offscreen python3 -m pytest tests/core/test_settings.py -v
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
- [Plugin Authoring](guides/plugin-authoring.md) - Package, install, enable, and test an external plugin
- [Extension Guide](guides/extension-guide.md) - Overview of extension points
- [Adding Formats](guides/adding-formats.md) - Create new annotation formats
- [Adding Features](guides/adding-features.md) - Add new actions and UI
- [i18n Guide](guides/i18n-guide.md) - Add new languages
- [Optional Dependencies](guides/optional-dependencies.md) - Install SAM, video, and profiling extras
- [Smart Video Annotation](features/smart-video-annotation.md) - Annotate and export tracked video frames
- [Testing Plan](testing-plan.md) - Test audit findings and roadmap

### Reference
- [Plugin API Major 1](reference/plugin-api-v1.md) - Public plugin contract and deprecation policy
- [Keyboard Shortcuts](reference/keyboard-shortcuts.md) - Complete hotkey reference
- [Settings](reference/settings.md) - Configuration options
- [Troubleshooting](reference/troubleshooting.md) - Common issues and solutions
