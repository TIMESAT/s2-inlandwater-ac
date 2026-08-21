import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import patch

from s2_water_ac.backends import BACKENDS
from s2_water_ac.backends.base import Backend
from s2_water_ac.errors import RunFailed
from s2_water_ac.models import BackendStatus, PreparedCommand, ProductInfo
from s2_water_ac.products import inspect_product
from s2_water_ac.runner import run_product

from .helpers import make_safe


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, create_output: bool = True):
        self.create_output = create_output

    def doctor(self, executable: Optional[str] = None) -> BackendStatus:
        del executable
        return BackendStatus(self.name, True, Path(sys.executable), "test")

    def prepare(
        self,
        product: ProductInfo,
        input_path: Path,
        output_dir: Path,
        profile: str,
        resolution: int,
        parameters: Dict[str, str],
        executable: Optional[str],
        write_files: bool,
    ) -> PreparedCommand:
        del product, input_path, profile, resolution, parameters, executable, write_files
        target = output_dir / "result.nc"
        code = "from pathlib import Path; Path({!r}).write_text('ok')".format(str(target))
        if not self.create_output:
            code = "print('finished without output')"
        return PreparedCommand(
            argv=[sys.executable, "-c", code],
            output_paths=[target],
        )


class WorkingDirectoryBackend(FakeBackend):
    name = "fake-cwd"

    def prepare(
        self,
        product: ProductInfo,
        input_path: Path,
        output_dir: Path,
        profile: str,
        resolution: int,
        parameters: Dict[str, str],
        executable: Optional[str],
        write_files: bool,
    ) -> PreparedCommand:
        del product, input_path, profile, resolution, parameters, executable
        working_directory = output_dir / "work"
        if write_files:
            working_directory.mkdir(parents=True, exist_ok=True)
        target = output_dir / "cwd.txt"
        code = "from pathlib import Path; Path({!r}).write_text(str(Path.cwd()))".format(
            str(target)
        )
        return PreparedCommand(
            argv=[sys.executable, "-c", code],
            output_paths=[target],
            working_directory=working_directory,
        )


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.product = inspect_product(str(make_safe(self.root)))
        BACKENDS["fake"] = FakeBackend()
        BACKENDS["fake-cwd"] = WorkingDirectoryBackend()

    def tearDown(self) -> None:
        BACKENDS.pop("fake", None)
        BACKENDS.pop("fake-cwd", None)
        BACKENDS.pop("fake-missing", None)
        self.temporary.cleanup()

    def test_run_records_success_and_skips_completed_output(self) -> None:
        output = self.root / "outputs"
        result = run_product(self.product, "fake", output)
        self.assertEqual(result["status"], "success")
        manifest_path = output / self.product.product_id / "fake" / "run.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "success")
        skipped = run_product(self.product, "fake", output)
        self.assertEqual(skipped["status"], "skipped")

    def test_zero_exit_without_output_is_failure(self) -> None:
        backend = FakeBackend(create_output=False)
        backend.name = "fake-missing"
        BACKENDS[backend.name] = backend
        with self.assertRaises(RunFailed) as context:
            run_product(self.product, backend.name, self.root / "outputs")
        self.assertEqual(context.exception.returncode, 3)

    def test_dry_run_has_no_output_side_effect(self) -> None:
        output = self.root / "dry"
        result = run_product(self.product, "fake", output, dry_run=True)
        self.assertEqual(result["status"], "dry-run")
        self.assertFalse(output.exists())

    def test_backend_can_use_an_isolated_working_directory(self) -> None:
        output = self.root / "outputs"
        result = run_product(self.product, "fake-cwd", output)
        working_directory = output / self.product.product_id / "fake-cwd" / "work"
        cwd_path = working_directory.parent / "cwd.txt"
        self.assertEqual(
            Path(cwd_path.read_text(encoding="utf-8")).resolve(),
            working_directory.resolve(),
        )
        self.assertEqual(
            Path(str(result["working_directory"])).resolve(),
            working_directory.resolve(),
        )

    def test_ocsmart_runs_from_generated_official_settings(self) -> None:
        home = self.root / "ocsmart"
        (home / "src").mkdir(parents=True)
        (home / "auxdata").mkdir()
        launcher = home / "OCSMART.py"
        launcher.write_text(
            "from pathlib import Path\n"
            "settings = {}\n"
            "for line in Path('OCSMART_Input.txt').read_text().splitlines():\n"
            "    key, value = line.split('=', 1)\n"
            "    settings[key.strip()] = value.strip()\n"
            "source = next(Path(settings['l1b_path']).iterdir())\n"
            "target = Path(settings['l2_path']) / "
            "(source.stem + '_L2_OCSMART.h5')\n"
            "target.write_text('ok')\n",
            encoding="utf-8",
        )
        output = self.root / "ocsmart-output"
        environment = {
            "OCSMART_PYTHON": sys.executable,
            "OCSMART_CACHE": str(self.root / "ocsmart-cache"),
        }
        with patch.dict(os.environ, environment, clear=False):
            result = run_product(
                self.product,
                "ocsmart",
                output,
                parameters={"l2_prod": "rrs,chl,tsm"},
                executable=str(launcher),
            )
        result_dir = output / self.product.product_id / "ocsmart"
        self.assertEqual(result["status"], "success")
        self.assertTrue(
            (result_dir / "{}_L2_OCSMART.h5".format(self.product.product_id)).is_file()
        )
        settings = (
            result_dir / ".ocsmart-runtime" / "OCSMART_Input.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("l2_prod = rrs,chl,tsm", settings)
        self.assertTrue((result_dir / ".ocsmart-runtime" / "anc").is_symlink())


if __name__ == "__main__":
    unittest.main()
