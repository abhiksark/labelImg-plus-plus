labelImg++
==========

.. image:: https://img.shields.io/pypi/v/labelImgPlusPlus.svg
        :target: https://pypi.org/project/labelImgPlusPlus/

.. image:: https://img.shields.io/pypi/dm/labelImgPlusPlus.svg
        :target: https://pypi.org/project/labelImgPlusPlus/

.. image:: https://github.com/abhiksark/labelImg-plus-plus/actions/workflows/ci.yaml/badge.svg
        :target: https://github.com/abhiksark/labelImg-plus-plus/actions

**labelImg++** 是增強版影像標註工具，基於 `LabelImg <https://github.com/tzutalin/labelImg>`__ 開發。

使用 Python 和 PyQt5 開發，支持 PASCAL VOC、YOLO、CreateML 格式。

.. image:: https://raw.githubusercontent.com/tzutalin/labelImg/master/demo/demo3.jpg
     :alt: Demo Image

labelImg++ 新功能
-----------------

圖庫模式
~~~~~~~~

按 **Ctrl+G** 或點擊工具欄中的 **圖庫模式** 按鈕，打開全屏圖庫視圖。

- 縮略圖顯示標註狀態：
  - **灰色邊框**：無標籤
  - **藍色邊框**：有標籤
  - **綠色邊框**：已驗證
- 使用滑塊調整縮略圖大小（40px - 300px）
- **雙擊** 縮略圖載入該圖像

安裝
----

從 PyPI 安裝（Python 3.6+）
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: shell

    pip3 install labelImgPlusPlus
    labelImgPlusPlus
    labelImgPlusPlus [IMAGE_PATH] [PRE-DEFINED CLASS FILE]

從源碼編譯
~~~~~~~~~~

**Ubuntu/Linux:**

.. code:: shell

    sudo apt-get install pyqt5-dev-tools
    sudo pip3 install -r requirements/requirements-linux-python3.txt
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

快捷鍵
------

+--------------------+--------------------------------------------+
| Ctrl + u           | 讀取所有影像從每個目錄                     |
+--------------------+--------------------------------------------+
| Ctrl + r           | 改變標示結果的存檔目錄                     |
+--------------------+--------------------------------------------+
| Ctrl + s           | 存檔                                       |
+--------------------+--------------------------------------------+
| Ctrl + d           | 複製目前的標籤和物件的區塊                 |
+--------------------+--------------------------------------------+
| Ctrl + Shift + d   | 刪除目前影像                               |
+--------------------+--------------------------------------------+
| Ctrl + g           | 切換圖庫模式                               |
+--------------------+--------------------------------------------+
| Space              | 標示目前照片已經處理過                     |
+--------------------+--------------------------------------------+
| w                  | 產生新的物件區塊                           |
+--------------------+--------------------------------------------+
| d                  | 下張影像                                   |
+--------------------+--------------------------------------------+
| a                  | 上張影像                                   |
+--------------------+--------------------------------------------+
| del                | 刪除所選的物件區塊                         |
+--------------------+--------------------------------------------+
| Ctrl + +           | 放大影像                                   |
+--------------------+--------------------------------------------+
| Ctrl + -           | 縮小影像                                   |
+--------------------+--------------------------------------------+
| ↑→↓←               | 移動所選的物件區塊                         |
+--------------------+--------------------------------------------+

授權
----

`MIT License <https://github.com/abhiksark/labelImg-plus-plus/blob/master/LICENSE>`_

基於 `Tzutalin <https://github.com/tzutalin>`__ 的 LabelImg (2015)。
