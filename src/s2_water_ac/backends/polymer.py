import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from ..errors import ConfigurationError
from ..models import BackendStatus, PreparedCommand, ProductInfo
from .base import Backend, env_path, first_existing, resolve_program, validate_parameters


class PolymerBackend(Backend):
    name = "polymer"
    summary = "HYGEOS POLYMER，联合处理气溶胶与耀斑"
    requires_directory = True

    def _resolve(self, executable: Optional[str]) -> Optional[Path]:
        if executable:
            return resolve_program(executable)
        current_python = Path(sys.executable).resolve()
        return first_existing(
            (
                env_path("POLYMER_PYTHON"),
                env_path("POLYMER_CLI"),
                current_python if importlib.util.find_spec("polymer") else None,
                resolve_program("polymer_cli.py"),
                resolve_program("polymer_cli"),
            )
        )

    @staticmethod
    def _is_minimal_cli(executable: Path) -> bool:
        return "polymer_cli" in executable.name

    def doctor(self, executable: Optional[str] = None) -> BackendStatus:
        resolved = self._resolve(executable)
        if resolved is None:
            return BackendStatus(
                self.name,
                False,
                None,
                "未找到 POLYMER；设置 POLYMER_PYTHON（推荐）或 POLYMER_CLI",
            )
        if self._is_minimal_cli(resolved):
            detail = "已找到 POLYMER 最小 CLI（其 MSI 输出固定使用默认 60 m）"
        else:
            detail = "已找到 POLYMER Python；可使用 10/20/60 m 和 SAFE 内嵌 ECMWF 辅助数据"
        return BackendStatus(self.name, True, resolved, detail)

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
        del profile, write_files
        validate_parameters(parameters)
        runner = self.require_executable(executable)
        target = output_dir / "{}_polymer.nc".format(product.product_id)
        if self._is_minimal_cli(runner):
            if resolution != 60 or parameters:
                raise ConfigurationError(
                    "POLYMER 最小 CLI 不支持分辨率/高级参数；请设置 POLYMER_PYTHON"
                )
            argv = [str(runner), str(input_path), str(target), "-fmt", "netcdf4"]
            notes = ["POLYMER 最小 CLI 使用 MSI 默认 60 m 分辨率。"]
        else:
            allowed = {
                "ancillary", "multiprocessing", "blocksize", "sline", "eline",
                "scol", "ecol", "altitude", "use_srf",
            }
            unknown = sorted(set(parameters).difference(allowed))
            if unknown:
                raise ConfigurationError(
                    "POLYMER 不支持这些 --set 参数：{}".format(", ".join(unknown))
                )
            driver = Path(__file__).resolve().parent.parent / "polymer_driver.py"
            argv = [
                str(runner),
                str(driver),
                str(input_path),
                str(target),
                "--resolution",
                str(resolution),
            ]
            effective = {"ancillary": "embedded", "multiprocessing": "0"}
            effective.update(parameters)
            for key, value in effective.items():
                argv.extend(["--{}".format(key.replace("_", "-")), value])
            notes = ["默认读取 SAFE 内 AUX_ECMWFT；可用 --set ancillary=nasa 改用 NASA 辅助数据。"]
        return PreparedCommand(argv=argv, output_paths=[target], notes=notes)

