import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional

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


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.product = inspect_product(str(make_safe(self.root)))
        BACKENDS["fake"] = FakeBackend()

    def tearDown(self) -> None:
        BACKENDS.pop("fake", None)
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


if __name__ == "__main__":
    unittest.main()
