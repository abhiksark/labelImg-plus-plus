# Additional tools

## Convert the label files to CSV

### Introduction
To train an object-detection model on Google Cloud, prepare a CSV file in the [Vertex AI object-detection import format](https://cloud.google.com/vertex-ai/docs/image-data/object-detection/prepare-data#csv).

`label_to_csv.py` converts YOLO `txt` or Pascal VOC `xml` label files to that CSV format. The label files must follow the structure below.

### Structures
* Images
    To train the object detection tasks, all the images should upload to the cloud storage and access it by its name. All the images should stay in the **same buckets** in cloud storage. Also, different classes should have their own folder as below.
    ```
    <bucket_name> (on the cloud storage)
    | -- class1
    |    | -- class1_01.jpg
    |    | -- class1_02.jpg
    |    | ...
    | -- class2
    |    | -- class2_01.jpg
    |    | -- class2_02.jpg
    |    | ...
    | ...
    ```
    Note, URI of the `class1_01.jpg` is `gs://<bucket_name>/class1/class1_01.jpg`
* Labels
    There are four types of training data - `TRAINING`, `VALIDATION`, `TEST` and `UNASSIGNED`. To assign different categories, we should create four directories.
    Inside each folder, users should create the class folders with the same name in cloud storage (see below structure).
    ```
    labels (on PC)
    | -- TRAINING
    |    | -- class1
    |    |    | -- class1_01.txt (or .xml)
    |    |    | ...
    |    | -- class2
    |    |    | -- class2_01.txt (or .xml)
    |    |    | ...
    |    | ...
    | -- VALIDATION
    |    | -- class1
    |    |    | -- class1_02.txt (or .xml)
    |    |    | ...
    |    | -- class2
    |    |    | -- class2_02.txt (or .xml)
    |    |    | ...
    |    | ...
    | -- TEST
    |    | (same as TRAINING and VALIDATION)
    | -- UNASSIGNED
    |    | (same as TRAINING and VALIDATION)
    ```

### Usage

From the repository root, run:

```commandline
python tools/label_to_csv.py -h
```

```commandline
usage: label_to_csv.py [-h] -p PREFIX -l LOCATION -m {txt,xml} [-o OUTPUT]
                       [-c CLASSES]

options:
  -h, --help            show this help message and exit
  -p PREFIX, --prefix PREFIX
                        Cloud Storage bucket or gs:// path prefix
  -l LOCATION, --location LOCATION
                        Parent directory of the split label directories
  -m {txt,xml}, --mode {txt,xml}
                        Source annotation format
  -o OUTPUT, --output OUTPUT
                        Output CSV path (default: res.csv)
  -c CLASSES, --classes CLASSES
                        YOLO class names file (TXT mode only)
```

For example, with a bucket named **test**, labels in **/User/test/labels**, and YOLO TXT annotations:

```commandline
python tools/label_to_csv.py \
  -p test \
  -l /User/test/labels \
  -m txt
```

The output file is `res.csv` by default; use `--output PATH` to choose another location. TXT mode maps each YOLO class index through `--classes`, whose default is the repository's `data/predefined_classes.txt`. XML mode reads labels directly from each Pascal VOC file and does not use `--classes`.

Malformed annotations, unreadable inputs, and unwritable output paths produce a concise error and a nonzero exit status. After a successful export, upload the CSV file to Cloud Storage and import it into Vertex AI.
