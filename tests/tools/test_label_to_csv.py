"""Focused tests for the standalone Vertex AI CSV exporter."""

import csv
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "tools" / "label_to_csv.py"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("label_to_csv", str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPORTER = _load_exporter()


class LabelToCsvTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.labels = self.root / "labels"
        self.labels.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _class_dir(self, split="TRAINING", class_name="animals"):
        class_dir = self.labels / split / class_name
        class_dir.mkdir(parents=True, exist_ok=True)
        return class_dir

    def _run_cli(self, *arguments):
        # -S makes site-packages (including pandas, if installed) unavailable.
        return subprocess.run(
            [sys.executable, "-S", str(SCRIPT), *map(str, arguments)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_txt_cli_honors_custom_output_without_pandas(self):
        class_dir = self._class_dir()
        (class_dir / "sample.txt").write_text(
            "0   0.5\t0.5  0.4 0.2\n", encoding="utf-8"
        )
        # Neither a top-level file nor a file inside a split is a label folder.
        (self.labels / "notes.txt").write_text("ignored", encoding="utf-8")
        (self.labels / "TRAINING" / "metadata.json").write_text(
            "ignored", encoding="utf-8"
        )
        output = self.root / "custom.csv"

        result = self._run_cli(
            "--prefix",
            "gs://example-bucket/dataset/",
            "--location",
            self.labels,
            "--mode",
            "txt",
            "--output",
            output,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())
        self.assertFalse((self.root / "res.csv").exists())
        with output.open(newline="", encoding="utf-8") as csv_file:
            self.assertEqual(
                list(csv.reader(csv_file)),
                [[
                    "TRAINING",
                    "gs://example-bucket/dataset/animals/sample.jpg",
                    "dog",
                    "0.3",
                    "0.4",
                    "",
                    "",
                    "0.7",
                    "0.6",
                    "",
                    "",
                ]],
            )

    def test_voc_cli_preserves_normalized_two_vertex_schema(self):
        class_dir = self._class_dir("VALIDATION", "dogs")
        (class_dir / "frame.xml").write_text(
            """<annotation>
  <size><width>200</width><height>100</height></size>
  <object>
    <name>dog</name>
    <bndbox><xmin>20</xmin><ymin>10</ymin><xmax>180</xmax><ymax>90</ymax></bndbox>
  </object>
</annotation>
""",
            encoding="utf-8",
        )
        output = self.root / "voc.csv"

        result = self._run_cli(
            "-p",
            "example-bucket",
            "-l",
            self.labels,
            "-m",
            "xml",
            "-c",
            self.root / "does-not-exist.txt",
            "-o",
            output,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        with output.open(newline="", encoding="utf-8") as csv_file:
            rows = list(csv.reader(csv_file))
        self.assertEqual(
            rows,
            [[
                "VALIDATION",
                "gs://example-bucket/dogs/frame.jpg",
                "dog",
                "0.1",
                "0.1",
                "",
                "",
                "0.9",
                "0.9",
                "",
                "",
            ]],
        )
        self.assertEqual(len(rows[0]), 11)

    def test_txt_malformed_line_is_actionable_and_does_not_write_output(self):
        class_dir = self._class_dir()
        bad_label = class_dir / "bad.txt"
        bad_label.write_text("0 0.5 0.5 0 0.2\n", encoding="utf-8")
        classes = self.root / "classes.txt"
        classes.write_text("animal\n", encoding="utf-8")
        output = self.root / "bad.csv"

        result = self._run_cli(
            "-p",
            "bucket",
            "-l",
            self.labels,
            "-m",
            "txt",
            "-c",
            classes,
            "-o",
            output,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("bad.txt: line 1", result.stderr)
        self.assertIn("greater than zero", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(output.exists())

    def test_txt_decode_error_is_contextual(self):
        class_dir = self._class_dir()
        bad_label = class_dir / "bad-encoding.txt"
        bad_label.write_bytes(b"\xff\xfe\xfd")

        with self.assertRaisesRegex(
            EXPORTER.ExportError, r"cannot read .*bad-encoding\.txt"
        ):
            EXPORTER.txt2csv(
                class_dir, "TRAINING", "gs://bucket/animals", ["animal"]
            )

    def test_voc_nonpositive_size_is_actionable(self):
        class_dir = self._class_dir()
        bad_label = class_dir / "bad.xml"
        bad_label.write_text(
            "<annotation><size><width>0</width><height>100</height></size></annotation>",
            encoding="utf-8",
        )

        result = self._run_cli(
            "-p", "bucket", "-l", self.labels, "-m", "xml"
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("bad.xml", result.stderr)
        self.assertIn("greater than zero", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "res.csv").exists())

    def test_unit_validation_rejects_missing_input_and_empty_classes(self):
        with self.assertRaisesRegex(EXPORTER.ExportError, "does not exist"):
            EXPORTER.export_rows(
                self.root / "missing", "xml", "bucket", class_labels=None
            )
        with self.assertRaisesRegex(EXPORTER.ExportError, "non-empty classes"):
            EXPORTER.export_rows(self.labels, "txt", "bucket", class_labels=[])


if __name__ == "__main__":
    unittest.main()
