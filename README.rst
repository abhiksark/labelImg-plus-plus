labelImg++
==========

.. image:: https://img.shields.io/badge/python-3.6+-blue.svg
        :target: https://www.python.org/downloads/

.. image:: https://img.shields.io/badge/license-MIT-green.svg
        :target: https://github.com/abhiksark/labelImg-plus-plus/blob/master/LICENSE

**labelImg++** is an enhanced graphical image annotation tool, forked from the original `LabelImg <https://github.com/tzutalin/labelImg>`__ by Tzutalin.

It is written in Python and uses PyQt5 for its graphical interface. Annotations are saved in PASCAL VOC (XML), YOLO (TXT), and CreateML (JSON) formats.

.. image:: https://raw.githubusercontent.com/tzutalin/labelImg/master/demo/demo3.jpg
     :alt: Demo Image

New Features in labelImg++
--------------------------

Gallery Mode
~~~~~~~~~~~~

Press **Ctrl+G** or click the **Gallery Mode** button in the toolbar to open a full-screen gallery view of all images in the current directory.

- Thumbnails display annotation status with colored borders:
  - **Gray border**: No labels
  - **Blue border**: Has labels
  - **Green border**: Verified
- Use the **size slider** to adjust thumbnail size (40px - 300px)
- **Double-click** a thumbnail to load that image
- Close the gallery window to return to normal view

Installation
------------

From PyPI (Python 3.6+)
~~~~~~~~~~~~~~~~~~~~~~~

.. code:: shell

    pip3 install labelImg
    labelImg
    labelImg [IMAGE_PATH] [PRE-DEFINED CLASS FILE]

Build from Source
~~~~~~~~~~~~~~~~~

**Ubuntu/Linux:**

.. code:: shell

    sudo apt-get install pyqt5-dev-tools
    sudo pip3 install -r requirements/requirements-linux-python3.txt
    make qt5py3
    python3 labelImg.py

**macOS:**

.. code:: shell

    pip3 install pyqt5 lxml
    make qt5py3
    python3 labelImg.py

**Windows:**

.. code:: shell

    pip install pyqt5 lxml
    pyrcc5 -o libs/resources.py resources.qrc
    python labelImg.py

Usage
-----

1. Click **Open Dir** to load images from a directory
2. Click **Create RectBox** or press **W** to draw bounding boxes
3. Click and drag to annotate objects
4. Press **Ctrl+S** to save annotations
5. Use **D** and **A** to navigate between images

Supported Formats
~~~~~~~~~~~~~~~~~

- **PASCAL VOC** (.xml) - Used by ImageNet
- **YOLO** (.txt) - Normalized coordinates
- **CreateML** (.json) - Apple's format

Hotkeys
-------

+--------------------+--------------------------------------------+
| Ctrl + u           | Load all images from a directory           |
+--------------------+--------------------------------------------+
| Ctrl + r           | Change default annotation target dir       |
+--------------------+--------------------------------------------+
| Ctrl + s           | Save                                       |
+--------------------+--------------------------------------------+
| Ctrl + d           | Copy current label and rect box            |
+--------------------+--------------------------------------------+
| Ctrl + Shift + d   | Delete current image                       |
+--------------------+--------------------------------------------+
| Ctrl + g           | Toggle Gallery Mode                        |
+--------------------+--------------------------------------------+
| Space              | Flag image as verified                     |
+--------------------+--------------------------------------------+
| w                  | Create a rect box                          |
+--------------------+--------------------------------------------+
| d                  | Next image                                 |
+--------------------+--------------------------------------------+
| a                  | Previous image                             |
+--------------------+--------------------------------------------+
| del                | Delete selected rect box                   |
+--------------------+--------------------------------------------+
| Ctrl + +           | Zoom in                                    |
+--------------------+--------------------------------------------+
| Ctrl + -           | Zoom out                                   |
+--------------------+--------------------------------------------+
| Arrow keys         | Move selected rect box                     |
+--------------------+--------------------------------------------+

Predefined Classes
------------------

Edit ``data/predefined_classes.txt`` to customize label options.

Reset Settings
--------------

If you encounter issues, remove the settings file:

.. code:: shell

    rm ~/.labelImgSettings.pkl

Or use **Menu > File > Reset All**

License
-------

`MIT License <https://github.com/abhiksark/labelImg-plus-plus/blob/master/LICENSE>`_

Based on `LabelImg <https://github.com/HumanSignal/labelImg>`__ by `Tzutalin <https://github.com/tzutalin>`__ (2015).
