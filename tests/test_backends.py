import tempfile
import unittest
from pathlib import Path

from s2_water_ac.backends.acolite import AcoliteBackend
from s2_water_ac.backends.c2rcc import C2rccBackend
from s2_water_ac.backends.polymer import PolymerBackend
from s2_water_ac.errors import ConfigurationError
from s2_water_ac.products import inspect_product

from .helpers import make_safe


class BackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.safe = make_safe(self.root)
        self.product = inspect_product(str(self.safe))
        self.executable = "/bin/echo"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_acolite_writes_inland_settings(self) -> None:
        output = self.root / "output"
        prepared = AcoliteBackend().prepare(
            self.product, self.safe, output, "inland", 20,
            {"dsf_write_aot_550": "True"}, self.executable, True,
        )
        settings = (output / "acolite-settings.txt").read_text(encoding="utf-8")
        self.assertIn("l2w_parameters=Rrs_*", settings)
        self.assertIn("s2_target_res=20", settings)
        self.assertIn("dsf_write_aot_550=True", settings)
        self.assertIn("--cli", prepared.argv)

    def test_c2rcc_uses_complex_nets_and_metadata_input(self) -> None:
        prepared = C2rccBackend().prepare(
            self.product, self.safe, self.root / "output", "inland", 20,
            {}, self.executable, False,
        )
        self.assertIn("-PnetSet=C2X-COMPLEX-Nets", prepared.argv)
        self.assertIn("-PoutputAsRrs=true", prepared.argv)
        source = next(value for value in prepared.argv if value.startswith("-SsourceProduct="))
        self.assertTrue(source.endswith("/MTD_MSIL1C.xml"))

    def test_macos_partition_gpt_is_rejected(self) -> None:
        status = C2rccBackend().doctor("/usr/sbin/gpt")
        self.assertFalse(status.available)

    def test_polymer_python_uses_driver_and_resolution(self) -> None:
        prepared = PolymerBackend().prepare(
            self.product, self.safe, self.root / "output", "inland", 20,
            {}, self.executable, False,
        )
        self.assertTrue(prepared.argv[1].endswith("polymer_driver.py"))
        self.assertIn("20", prepared.argv)
        self.assertIn("embedded", prepared.argv)

    def test_polymer_minimal_cli_rejects_20m(self) -> None:
        fake = self.root / "polymer_cli.py"
        fake.write_text("#!/bin/sh\n", encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            PolymerBackend().prepare(
                self.product, self.safe, self.root / "output", "inland", 20,
                {}, str(fake), False,
            )

if __name__ == "__main__":
    unittest.main()
