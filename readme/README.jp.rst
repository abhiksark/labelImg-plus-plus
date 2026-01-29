labelImg++
==========

.. image:: https://img.shields.io/pypi/v/labelImgPlusPlus.svg
        :target: https://pypi.org/project/labelImgPlusPlus/

.. image:: https://img.shields.io/pypi/dm/labelImgPlusPlus.svg
        :target: https://pypi.org/project/labelImgPlusPlus/

.. image:: https://github.com/abhiksark/labelImg-plus-plus/actions/workflows/ci.yaml/badge.svg
        :target: https://github.com/abhiksark/labelImg-plus-plus/actions

**labelImg++** は、`LabelImg <https://github.com/tzutalin/labelImg>`__ をベースにした拡張版アノテーションツールです。

PythonとPyQt5で開発され、PASCAL VOC、YOLO、CreateML形式をサポートしています。

.. image:: https://raw.githubusercontent.com/tzutalin/labelImg/master/demo/demo3.jpg
     :alt: Demo Image

labelImg++ の新機能
-------------------

ギャラリーモード
~~~~~~~~~~~~~~~~

**Ctrl+G** を押すか、ツールバーの **ギャラリーモード** ボタンをクリックして、フルスクリーンギャラリービューを開きます。

- サムネイルはアノテーション状態を表示：
  - **グレーの枠**：ラベルなし
  - **青い枠**：ラベルあり
  - **緑の枠**：検証済み
- スライダーでサムネイルサイズを調整（40px - 300px）
- サムネイルを **ダブルクリック** して画像を読み込む

インストール方法
----------------

PyPIからインストール（Python 3.6以降）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: shell

    pip3 install labelImgPlusPlus
    labelImgPlusPlus
    labelImgPlusPlus [IMAGE_PATH] [PRE-DEFINED CLASS FILE]

ソースからビルド
~~~~~~~~~~~~~~~~

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

ショートカット一覧
------------------

+--------------------+--------------------------------------------+
| Ctrl + u           | そのディレクトリの画像を読み込む           |
+--------------------+--------------------------------------------+
| Ctrl + r           | アノテーションの生成ディレクトリを変更     |
+--------------------+--------------------------------------------+
| Ctrl + s           | 保存する                                   |
+--------------------+--------------------------------------------+
| Ctrl + d           | 現在選択している矩形をコピー               |
+--------------------+--------------------------------------------+
| Ctrl + Shift + d   | 現在表示している画像を削除                 |
+--------------------+--------------------------------------------+
| Ctrl + g           | ギャラリーモードを切り替え                 |
+--------------------+--------------------------------------------+
| Space              | 現在の画像に検証済みフラグを立てる         |
+--------------------+--------------------------------------------+
| w                  | 矩形を生成する                             |
+--------------------+--------------------------------------------+
| d                  | 次の画像へ移動する                         |
+--------------------+--------------------------------------------+
| a                  | 前の画像へ移動する                         |
+--------------------+--------------------------------------------+
| del                | 選択した矩形を削除                         |
+--------------------+--------------------------------------------+
| Ctrl + +           | 画像を拡大                                 |
+--------------------+--------------------------------------------+
| Ctrl + -           | 画像を縮小                                 |
+--------------------+--------------------------------------------+
| ↑→↓←               | 十字キーで矩形を移動する                   |
+--------------------+--------------------------------------------+

ライセンス
----------

`MIT License <https://github.com/abhiksark/labelImg-plus-plus/blob/master/LICENSE>`_

`Tzutalin <https://github.com/tzutalin>`__ の LabelImg (2015) をベースにしています。
