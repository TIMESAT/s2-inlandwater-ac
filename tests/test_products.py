import tempfile
import unittest
import zipfile
from pathlib import Path

from s2_water_ac.errors import InputError
from s2_water_ac.products import discover_products, inspect_product, materialized_product

from .helpers import PRODUCT_ID, make_safe, make_zip


class ProductTests(unittest.TestCase):
    def test_inspects_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            safe = make_safe(Path(temporary))
            product = inspect_product(str(safe))
            self.assertEqual(product.product_id, PRODUCT_ID)
            self.assertEqual(product.platform, "S2A")
            self.assertEqual(product.tile_id, "33UVB")
            self.assertEqual(len(product.bands), 13)
            self.assertFalse(product.archive)

    def test_inspects_and_materializes_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = make_zip(Path(temporary))
            product = inspect_product(str(archive))
            self.assertTrue(product.archive)
            with materialized_product(product, require_directory=True) as safe:
                self.assertTrue((safe / "MTD_MSIL1C.xml").is_file())

    def test_discovery_prefers_safe_over_matching_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = make_zip(root)
            safe = root / (PRODUCT_ID + ".SAFE")
            self.assertTrue(archive.is_file())
            self.assertEqual(discover_products(str(root)), [safe.resolve()])

    def test_rejects_zip_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / (PRODUCT_ID + ".SAFE.zip")
            with zipfile.ZipFile(str(archive), "w") as output:
                output.writestr("../escape", "bad")
            with self.assertRaises(InputError):
                inspect_product(str(archive))

    def test_rejects_missing_band(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            safe = make_safe(Path(temporary))
            next(safe.rglob("*_B12.jp2")).unlink()
            with self.assertRaises(InputError):
                inspect_product(str(safe))


if __name__ == "__main__":
    unittest.main()
