import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from s2_water_ac.backends.acolite import AcoliteBackend
from s2_water_ac.backends.c2rcc import C2rccBackend
from s2_water_ac.backends.ocsmart import OcsmartBackend
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

    def test_c2rcc_resolves_snap_home_on_linux(self) -> None:
        snap_home = self.root / "esa-snap"
        gpt = snap_home / "bin" / "gpt"
        gpt.parent.mkdir(parents=True)
        gpt.write_text("#!/bin/sh\n", encoding="utf-8")
        with patch.dict(os.environ, {"SNAP_HOME": str(snap_home)}, clear=True):
            status = C2rccBackend().doctor()
        self.assertTrue(status.available)
        self.assertEqual(status.executable, gpt.resolve())

    def _make_ocsmart(self) -> Path:
        home = self.root / "ocsmart"
        (home / "src").mkdir(parents=True)
        (home / "auxdata").mkdir()
        launcher = home / "OCSMART.py"
        launcher.write_text("# test launcher\n", encoding="utf-8")
        return launcher

    def test_ocsmart_writes_isolated_input_and_uses_fixed_60m(self) -> None:
        launcher = self._make_ocsmart()
        output = self.root / "output"
        prepared = OcsmartBackend().prepare(
            self.product,
            self.safe,
            output,
            "inland",
            20,
            {"l2_prod": "rrs,chl,tsm", "block_size": "2048"},
            str(launcher),
            True,
        )
        runtime = output / ".ocsmart-runtime"
        settings = (runtime / "OCSMART_Input.txt").read_text(encoding="utf-8")
        self.assertIn("l2_prod = rrs,chl,tsm", settings)
        self.assertIn("block_size = 2048", settings)
        self.assertEqual(prepared.working_directory, runtime)
        self.assertEqual(prepared.argv[1], str(launcher.resolve()))
        self.assertEqual((runtime / "input" / self.safe.name).resolve(), self.safe.resolve())
        self.assertEqual(
            (runtime / "auxdata").resolve(),
            (launcher.parent / "auxdata").resolve(),
        )
        self.assertTrue(prepared.output_paths[0].name.endswith("_L2_OCSMART.h5"))
        self.assertTrue(any("60 m" in note for note in prepared.notes))

    def test_ocsmart_rejects_managed_and_unknown_parameters(self) -> None:
        launcher = self._make_ocsmart()
        backend = OcsmartBackend()
        with self.assertRaises(ConfigurationError):
            backend.prepare(
                self.product, self.safe, self.root / "output", "inland", 20,
                {"l1b_path": "/tmp"}, str(launcher), False,
            )
        with self.assertRaises(ConfigurationError):
            backend.prepare(
                self.product, self.safe, self.root / "output", "inland", 20,
                {"not_a_parameter": "1"}, str(launcher), False,
            )

    def test_ocsmart_doctor_rejects_incomplete_installation(self) -> None:
        launcher = self.root / "OCSMART.py"
        launcher.write_text("# incomplete\n", encoding="utf-8")
        status = OcsmartBackend().doctor(str(launcher))
        self.assertFalse(status.available)
        self.assertIn("src", status.detail)
        self.assertIn("auxdata", status.detail)

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
