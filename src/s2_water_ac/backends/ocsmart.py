import os
import sys
from pathlib import Path
from typing import Dict, Optional

from ..errors import ConfigurationError
from ..models import BackendStatus, PreparedCommand, ProductInfo
from .base import Backend, env_path, first_existing, resolve_program, validate_parameters


class OcsmartBackend(Backend):
    name = "ocsmart"
    summary = "OC-SMART 科学机器学习大气校正与水色反演"
    requires_directory = True

    _managed_parameters = {"l1b_path", "l2_path"}
    _allowed_parameters = {
        "l2_prod",
        "solz_limit",
        "senz_limit",
        "block_size",
        "geo_path",
        "north",
        "south",
        "east",
        "west",
        "latitude_center",
        "longitude_center",
        "box_width",
        "box_height",
        "start_line",
        "end_line",
        "start_pixel",
        "end_pixel",
    }

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[3]

    def _python(self) -> str:
        configured = os.environ.get("OCSMART_PYTHON")
        if configured:
            return configured
        local = self._project_root() / ".external" / "envs" / "ocsmart" / "bin" / "python"
        return str(local) if local.is_file() else sys.executable

    def _resolve(self, executable: Optional[str]) -> Optional[Path]:
        if executable:
            return resolve_program(executable)
        configured_home = os.environ.get("OCSMART_HOME")
        external_root = self._project_root() / ".external"
        local_root = external_root / "ocsmart"
        nested = sorted(local_root.glob("*/OCSMART.py")) if local_root.is_dir() else []
        official = sorted(
            external_root.glob("OC-SMART_Python_Linux_v*/OCSMART.py"),
            reverse=True,
        )
        return first_existing(
            (
                env_path("OCSMART_LAUNCHER"),
                Path(configured_home) / "OCSMART.py" if configured_home else None,
                local_root / "OCSMART.py",
                *nested,
                *official,
                Path("/opt/ocsmart/OCSMART.py"),
                resolve_program("OCSMART.py"),
            )
        )

    @staticmethod
    def _missing_resources(launcher: Path) -> list:
        required = (launcher.parent / "src", launcher.parent / "auxdata")
        return [path.name for path in required if not path.is_dir()]

    def doctor(self, executable: Optional[str] = None) -> BackendStatus:
        launcher = self._resolve(executable)
        if launcher is None:
            return BackendStatus(
                self.name,
                False,
                None,
                "未找到 OC-SMART；设置 OCSMART_HOME 或 OCSMART_LAUNCHER",
            )
        missing = self._missing_resources(launcher)
        if missing:
            return BackendStatus(
                self.name,
                False,
                launcher,
                "OC-SMART 安装不完整，缺少：{}".format(", ".join(missing)),
            )
        python = resolve_program(self._python())
        if python is None:
            return BackendStatus(
                self.name,
                False,
                launcher,
                "未找到 OC-SMART Python：{}".format(self._python()),
            )
        return BackendStatus(
            self.name,
            True,
            launcher,
            "已找到 OC-SMART；Python={}".format(python),
        )

    @staticmethod
    def _with_separator(path: Path) -> str:
        value = str(path)
        return value if value.endswith(os.sep) else value + os.sep

    @staticmethod
    def _replace_generated_symlink(link: Path, target: Path) -> None:
        target = target.resolve()
        if link.is_symlink():
            if link.resolve(strict=False) == target:
                return
            link.unlink()
        elif link.exists():
            raise ConfigurationError(
                "拒绝替换 OC-SMART 运行目录中的非符号链接：{}".format(link)
            )
        link.symlink_to(target, target_is_directory=True)

    def _validate_backend_parameters(self, parameters: Dict[str, str]) -> None:
        validate_parameters(parameters)
        managed = sorted(set(parameters).intersection(self._managed_parameters))
        if managed:
            raise ConfigurationError(
                "OC-SMART 的输入和输出目录由统一入口管理，不能设置：{}".format(
                    ", ".join(managed)
                )
            )
        unknown = sorted(set(parameters).difference(self._allowed_parameters))
        if unknown:
            raise ConfigurationError(
                "OC-SMART 不支持这些 --set 参数：{}".format(", ".join(unknown))
            )

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
        del profile, resolution
        self._validate_backend_parameters(parameters)
        launcher = self.require_executable(executable)

        runtime_dir = output_dir / ".ocsmart-runtime"
        input_dir = runtime_dir / "input"
        input_link = input_dir / input_path.name
        auxdata_link = runtime_dir / "auxdata"
        settings_path = runtime_dir / "OCSMART_Input.txt"
        target = output_dir / "{}_L2_OCSMART.h5".format(product.product_id)

        settings = {
            "l1b_path": self._with_separator(input_dir),
            "l2_path": self._with_separator(output_dir),
            "l2_prod": "rrs,chl",
            "solz_limit": "70.0",
            "senz_limit": "70.0",
        }
        settings.update(parameters)

        generated_files = [settings_path, input_link, auxdata_link]
        if write_files:
            input_dir.mkdir(parents=True, exist_ok=True)
            self._replace_generated_symlink(input_link, input_path)
            self._replace_generated_symlink(auxdata_link, launcher.parent / "auxdata")

            cache = os.environ.get("OCSMART_CACHE")
            if cache:
                cache_root = Path(cache).expanduser().resolve()
                cache_root.mkdir(parents=True, exist_ok=True)
                for name in ("anc", "landmask_gsw"):
                    target_dir = cache_root / name
                    target_dir.mkdir(parents=True, exist_ok=True)
                    cache_link = runtime_dir / name
                    self._replace_generated_symlink(cache_link, target_dir)
                    generated_files.append(cache_link)

            settings_path.write_text(
                "\n".join("{} = {}".format(key, value) for key, value in settings.items())
                + "\n",
                encoding="utf-8",
            )

        return PreparedCommand(
            argv=[self._python(), str(launcher)],
            output_paths=[target],
            generated_files=generated_files,
            notes=[
                "OC-SMART Linux v2.2 对 Sentinel-2 固定使用 60 m；--resolution 不生效。",
                "默认输出 rrs,chl；可用 --set l2_prod=... 选择官方支持的产品。",
                "运行时可能从 NASA OB.DAAC 下载辅助数据，需要 Earthdata 授权。",
            ],
            working_directory=runtime_dir,
        )
