============
labelImg++
============

*A modern, enhanced image annotation tool for machine learning*

.. image:: https://img.shields.io/pypi/v/labelImgPlusPlus.svg
        :target: https://pypi.org/project/labelImgPlusPlus/

.. image:: https://img.shields.io/pypi/dm/labelImgPlusPlus.svg
        :target: https://pypi.org/project/labelImgPlusPlus/

.. image:: https://github.com/abhiksark/labelImg-plus-plus/actions/workflows/ci.yaml/badge.svg
        :target: https://github.com/abhiksark/labelImg-plus-plus/actions

.. image:: https://img.shields.io/badge/python-3.6+-blue.svg
        :target: https://www.python.org/downloads/

.. image:: https://img.shields.io/badge/license-MIT-green.svg
        :target: https://github.com/abhiksark/labelImg-plus-plus/blob/master/LICENSE

.. image:: https://sonarcloud.io/api/project_badges/measure?project=abhiksark_labelImg-plus-plus&metric=alert_status
        :target: https://sonarcloud.io/dashboard?id=abhiksark_labelImg-plus-plus

----

**labelImg++** is a powerful graphical image annotation tool for creating bounding box labels, designed for machine learning and computer vision projects. Forked from the original LabelImg with significant enhancements.

    **Version 2.0.0** - First stable release! Install with ``pip install labelImgPlusPlus``

.. image:: https://raw.githubusercontent.com/abhiksark/labelImg-plus-plus/c7fbd5fc08a561206b210706143a50023c82a782/resources/demo/demo.gif
     :alt: labelImg++ demo - gallery, bounding boxes, dark theme, polygons, keypoints and save
     :align: center

Features
--------

Core Annotation Features
~~~~~~~~~~~~~~~~~~~~~~~~

- **Multi-format support**: PASCAL VOC (XML), YOLO (TXT), CreateML (JSON)
- **Bounding box annotation** with drag-and-drop interface
- **Auto-save mode** for uninterrupted workflow
- **Predefined class labels** with customizable list
- **Verification system** to mark completed annotations

New in labelImg++ v2.0
~~~~~~~~~~~~~~~~~~~~~~

**Undo/Redo Support**
    Full undo/redo for all annotation actions. Press **Ctrl+Z** to undo and **Ctrl+Y** to redo. Never lose your work again!

**Gallery Mode with Annotation Preview**
    Visual thumbnail gallery showing all images with bounding box overlays directly on thumbnails.

    - Colored borders indicate status: Gray (no labels), Blue (has labels), Green (verified)
    - Bounding boxes visible on thumbnails with corner markers (less clutter for nested boxes)
    - Quick size presets (S/M/L/XL) plus slider for fine control
    - Smart selection: click on nested boxes selects the inner box
    - Press **Ctrl+G** to toggle gallery mode

**Modern UI with Feather Icons**
    Clean, modern interface with beautiful Feather icons and improved visual design.

**Responsive DPI Scaling**
    Icons and UI elements scale properly on high-DPI displays (4K, Retina).

**Expandable Toolbar**
    Click the chevron at the bottom of the toolbar to expand/collapse and show full button labels.

**Consolidated File Menu**
    Open File, Open Dir, and Change Save Dir combined into a single dropdown for cleaner toolbar.

**Brightness Adjustment**
    Adjust image brightness on-the-fly to better see annotations on dark or light images.

**Dark Mode Theme**
    Choose between light and dark themes for comfortable annotation in any lighting condition.

    - Press **Ctrl+Shift+T** to toggle between themes
    - Theme preference automatically saved
    - All UI components (canvas, gallery, dialogs) respect the active theme
    - See `Dark Mode Documentation <https://github.com/abhiksark/labelImg-plus-plus/blob/master/docs/features/dark-mode.md>`_ for detailed information

**SAM-Assisted Segmentation** (optional)
    Click once on an object to auto-generate a polygon, traced from a
    Segment-Anything mask. Install the optional extra and toggle **SAM Segment**:

    .. code:: shell

        pip install labelimgplusplus[sam]

    Runs the lightweight MobileSAM model on ONNX Runtime — a ~70 MB,
    CPU-friendly extra with no PyTorch dependency. Point **Tools → SAM
    Settings…** at your own exported encoder/decoder pair to use a different
    SAM variant. Without the extra installed, the action stays disabled (with
    an install hint) and nothing else changes.

Installation
------------

From PyPI (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~

**Note:** The command was renamed from ``labelImgPlusPlus`` to ``labelimgpp`` in v2.1.1. The old command still works but shows a deprecation warning.

.. code:: shell

    pip3 install labelimgplusplus
    labelimgpp

Or use the full command name:

.. code:: shell

    labelimgplusplus

With a specific image or directory:

.. code:: shell

    labelimgpp [IMAGE_PATH] [PRE-DEFINED CLASS FILE] [SAVE_DIR]

Build from Source
~~~~~~~~~~~~~~~~~

**Ubuntu/Linux:**

.. code:: shell

    sudo apt-get install pyqt5-dev-tools
    pip3 install -r requirements/requirements-linux-python3.txt
    make qt5py3
    python3 labelImgPlusPlus.py

**macOS:**

.. code:: shell

    pip3 install pyqt5 lxml
    make qt5py3
    python3 labelImgPlusPlus.py

**Windows:**

.. code:: shell

    pip install pyqt5 lxml
    pyrcc5 -o libs/resources.py resources.qrc
    python labelImgPlusPlus.py

Quick Start
-----------

1. **Open images**: Click the file dropdown button or press **Ctrl+U** to load a directory
2. **Create annotations**: Press **W** or click **Create RectBox**, then drag to draw
3. **Label objects**: Select a class from the popup dialog
4. **Save**: Press **Ctrl+S** to save annotations
5. **Navigate**: Use **D** (next) and **A** (previous) to move between images
6. **Review**: Press **Ctrl+G** for gallery mode to review all annotations

Supported Annotation Formats
----------------------------

+---------------+------------+------------------------------------------+
| Format        | Extension  | Description                              |
+===============+============+==========================================+
| PASCAL VOC    | .xml       | ImageNet format, absolute coordinates    |
+---------------+------------+------------------------------------------+
| YOLO          | .txt       | Normalized coordinates (0-1), with       |
|               |            | classes.txt for class names              |
+---------------+------------+------------------------------------------+
| CreateML      | .json      | Apple's ML format for iOS/macOS          |
+---------------+------------+------------------------------------------+

Keyboard Shortcuts
------------------

**File Operations**

+--------------------+--------------------------------------------+
| Ctrl + O           | Open file                                  |
+--------------------+--------------------------------------------+
| Ctrl + U           | Open directory                             |
+--------------------+--------------------------------------------+
| Ctrl + R           | Change save directory                      |
+--------------------+--------------------------------------------+
| Ctrl + S           | Save current annotation                    |
+--------------------+--------------------------------------------+
| Ctrl + Shift + S   | Save as                                    |
+--------------------+--------------------------------------------+

**Navigation**

+--------------------+--------------------------------------------+
| D                  | Next image                                 |
+--------------------+--------------------------------------------+
| A                  | Previous image                             |
+--------------------+--------------------------------------------+
| Ctrl + G           | Toggle Gallery Mode                        |
+--------------------+--------------------------------------------+

**Annotation**

+--------------------+--------------------------------------------+
| W                  | Create bounding box                        |
+--------------------+--------------------------------------------+
| Ctrl + Z           | Undo                                       |
+--------------------+--------------------------------------------+
| Ctrl + Y           | Redo                                       |
+--------------------+--------------------------------------------+
| Ctrl + D           | Duplicate selected box                     |
+--------------------+--------------------------------------------+
| Del                | Delete selected box                        |
+--------------------+--------------------------------------------+
| Space              | Mark image as verified                     |
+--------------------+--------------------------------------------+
| Arrow keys         | Move selected box                          |
+--------------------+--------------------------------------------+

**View**

+--------------------+--------------------------------------------+
| Ctrl + +           | Zoom in                                    |
+--------------------+--------------------------------------------+
| Ctrl + -           | Zoom out                                   |
+--------------------+--------------------------------------------+
| Ctrl + F           | Fit window                                 |
+--------------------+--------------------------------------------+
| Ctrl + Shift + F   | Fit width                                  |
+--------------------+--------------------------------------------+
| Ctrl + Shift + T   | Toggle dark mode theme                     |
+--------------------+--------------------------------------------+

Configuration
-------------

**Predefined Classes**

Edit ``data/predefined_classes.txt`` to customize the label options:

.. code::

    dog
    cat
    person
    car
    bicycle

**Reset Settings**

If you encounter issues, reset the settings:

.. code:: shell

    rm ~/.labelImgSettings.json

Or use **Menu > File > Reset All**

Roadmap
-------

**v2.0.0 (Stable)** - *Current*
    First stable release with bug fixes and UX improvements

    - Silent error handling fixed
    - YOLO format crash on missing classes.txt fixed
    - Format change warning dialog added
    - Save location visibility in title bar
    - Auto-save menu items clarified
    - Gallery status color legend added
    - Progress indicator for large directories
    - Gallery size presets (S/M/L/XL buttons)
    - Corner markers on thumbnails for cleaner nested box display
    - Improved nested bounding box selection (smallest box selected)
    - Gallery freeze fix for large directories

**v2.1.0** - *Planned*
    - Dark mode theme (Completed - use Ctrl+Shift+T to toggle)
    - Annotation review workflow
    - Dataset splitting tool (train/val/test)
    - Label consistency checker
    - Annotation statistics dashboard
    - Improved label dialog with search/filter
    - Keyboard shortcuts customization

**v2.2.0** - *Future*
    - Polygon annotation support
    - Recent files menu
    - Snap to grid / alignment guides
    - Multiple image annotation (batch labeling)

**v3.0.0** - *Vision*
    - Plugin architecture
    - COCO format support
    - Ultralytics/YOLOv8 direct export
    - FiftyOne dataset integration

See the `GitHub Issues <https://github.com/abhiksark/labelImg-plus-plus/issues>`_ for detailed feature tracking.

Contributing
------------

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (``git checkout -b feature/amazing-feature``)
3. Commit your changes (``git commit -m 'Add amazing feature'``)
4. Push to the branch (``git push origin feature/amazing-feature``)
5. Open a Pull Request

License
-------

`MIT License <https://github.com/abhiksark/labelImg-plus-plus/blob/master/LICENSE>`_

Based on LabelImg by Tzutalin.

Author
------

Maintained by `Abhik Sarkar <https://abhik.ai>`__

Acknowledgments
---------------

- Original LabelImg by Tzutalin
- `Feather Icons <https://feathericons.com/>`__ for modern iconography
- All contributors and users of labelImg++
