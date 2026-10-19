import tempfile
import unittest
from pathlib import Path

from source_config import find_local_source, load_mapping_text
from generate_public_data import DEFAULT_MAPPING, ROOT


class SourceConfigTests(unittest.TestCase):
    def test_generator_uses_ignored_mapping_in_standalone_project_root(self):
        self.assertEqual(DEFAULT_MAPPING, ROOT / "origin_mapping.txt")

    def test_discovers_private_zip_in_dados_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "dados_raw" / "weekly_report.zip"
            source.parent.mkdir()
            source.write_bytes(b"private")

            self.assertEqual(find_local_source(root), source)

    def test_ignores_excel_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "dados_raw"
            raw.mkdir()
            (raw / "~$leads.xlsx").write_bytes(b"lock")
            source = raw / "leads.csv"
            source.write_text("a,b\n1,2\n", encoding="utf-8")

            self.assertEqual(find_local_source(root), source)

    def test_prefers_zip_when_report_also_has_excel_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "dados_raw"
            raw.mkdir()
            excel = raw / "weekly.xlsx"
            archive = raw / "weekly.zip"
            excel.write_bytes(b"xlsx")
            archive.write_bytes(b"zip")

            self.assertEqual(find_local_source(root), archive)

    def test_can_prefer_xlsx_to_preserve_origin_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "dados_raw"
            raw.mkdir()
            excel = raw / "weekly.xlsx"
            archive = raw / "weekly.zip"
            excel.write_bytes(b"xlsx")
            archive.write_bytes(b"zip")

            self.assertEqual(find_local_source(root, prefer_suffix=".xlsx"), excel)

    def test_secret_mapping_takes_precedence_over_local_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_mapping = Path(tmp) / "teste.txt"
            local_mapping.write_text("local", encoding="utf-8")

            self.assertEqual(
                load_mapping_text(local_mapping, {"ORIGIN_MAPPING_TEXT": "secret"}),
                "secret",
            )

    def test_example_mapping_contains_no_real_source_number(self):
        example_path = Path(__file__).parents[1] / "origin_mapping.example.txt"
        example = example_path.read_text(encoding="utf-8")

        self.assertNotIn("0000000001", example)
        self.assertNotIn("0000000002", example)


if __name__ == "__main__":
    unittest.main()
