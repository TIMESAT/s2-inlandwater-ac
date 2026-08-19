import os
import sys
from pathlib import Path
from typing import Dict, Optional

from ..models import BackendStatus, PreparedCommand, ProductInfo
from .base import Backend, env_path, first_existing, resolve_program, validate_parameters


class AcoliteBackend(Backend):
    name = "acolite"
    summary = "ACOLITE Dark Spectrum Fitting，面向沿海和内陆水体"

    def _resolve(self, executable: Optional[str]) -> Optional[Path]:
        if executable:
            return resolve_program(executable)
        home = os.environ.get("ACOLITE_HOME")
        return first_existing(
            (
                env_path("ACOLITE_LAUNCHER"),
                Path(home) / "launch_acolite.py" if home else None,
                resolve_program("acolite"),
            )
        )

    def doctor(self, executable: Optional[str] = None) -> BackendStatus:
        resolved = self._resolve(executable)
        if resolved is None:
            return BackendStatus(
                self.name,
                False,
                None,
                "未找到 ACOLITE；设置 ACOLITE_HOME 或 ACOLITE_LAUNCHER",
            )
        detail = "已找到 ACOLITE 启动器"
        if resolved.suffix == ".py":
            detail += "；Python={}".format(os.environ.get("ACOLITE_PYTHON", sys.executable))
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
        validate_parameters(parameters)
        launcher = self.require_executable(executable)
        settings = {
            "atmospheric_correction_method": "dark_spectrum",
            "s2_target_res": str(resolution),
            "l2w_parameters": "Rrs_*",
            "l2r_export_geotiff": "True",
            "l2w_export_geotiff": "True",
        }
        if profile == "standard":
            settings.pop("l2w_parameters")
            settings.pop("l2w_export_geotiff")
        settings.update(parameters)

        settings_path = output_dir / "acolite-settings.txt"
        if write_files:
            output_dir.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                "\n".join("{}={}".format(key, value) for key, value in settings.items())
                + "\n",
                encoding="utf-8",
            )

        if launcher.suffix == ".py":
            python = os.environ.get("ACOLITE_PYTHON", sys.executable)
            argv = [python, str(launcher)]
        else:
            argv = [str(launcher)]
        argv.extend(
            [
                "--cli",
                "--nogfx",
                "--settings={}".format(settings_path),
                "--inputfile={}".format(input_path),
                "--output={}".format(output_dir),
            ]
        )
        return PreparedCommand(
            argv=argv,
            output_paths=[],
            output_globs=["**/*.nc"],
            generated_files=[settings_path],
            notes=["首次运行可能自动下载 ACOLITE LUT。"],
        )
