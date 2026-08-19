import os
from pathlib import Path
from typing import Dict, Optional

from ..models import BackendStatus, PreparedCommand, ProductInfo
from .base import Backend, env_path, first_existing, resolve_program, validate_parameters


class C2rccBackend(Backend):
    name = "c2rcc"
    summary = "ESA SNAP C2RCC/C2X，默认采用复杂内陆水体神经网络"

    def _resolve(self, executable: Optional[str]) -> Optional[Path]:
        if executable:
            resolved = resolve_program(executable)
            if resolved == Path("/usr/sbin/gpt"):
                return None
            return resolved
        home = Path.home()
        resolved = first_existing(
            (
                env_path("SNAP_GPT"),
                Path("/Applications/snap/bin/gpt"),
                Path("/Applications/SNAP.app/Contents/MacOS/gpt"),
                home / "Applications/snap/bin/gpt",
                Path("/opt/snap/bin/gpt"),
                resolve_program("gpt"),
            )
        )
        # macOS ships /usr/sbin/gpt, a disk partitioning utility. It must never
        # be mistaken for SNAP's Graph Processing Tool.
        return None if resolved == Path("/usr/sbin/gpt") else resolved

    def doctor(self, executable: Optional[str] = None) -> BackendStatus:
        resolved = self._resolve(executable)
        if resolved is None:
            return BackendStatus(
                self.name,
                False,
                None,
                "未找到 SNAP Graph Processing Tool；设置 SNAP_GPT（macOS 的 /usr/sbin/gpt 不是 SNAP）",
            )
        return BackendStatus(
            self.name,
            True,
            resolved,
            "已找到 SNAP GPT；还需在 SNAP 中安装 Optical Toolbox/C2RCC",
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
        del resolution, write_files
        validate_parameters(parameters)
        gpt = self.require_executable(executable)
        source = input_path / "MTD_MSIL1C.xml" if input_path.is_dir() else input_path
        target = output_dir / "{}_c2rcc.dim".format(product.product_id)
        defaults = {
            "netSet": "C2X-COMPLEX-Nets" if profile == "inland" else "C2RCC-Nets",
            "outputAsRrs": "true",
            "outputUncertainties": "true",
        }
        defaults.update(parameters)
        argv = [
            str(gpt),
            "c2rcc.msi",
            "-SsourceProduct={}".format(source),
            "-t",
            str(target),
            "-f",
            "BEAM-DIMAP",
        ]
        argv.extend("-P{}={}".format(key, value) for key, value in defaults.items())
        return PreparedCommand(
            argv=argv,
            output_paths=[target, target.with_suffix(".data")],
            notes=[
                "inland profile 使用 C2X-COMPLEX-Nets；输出反射率为 Rrs。",
                "C2RCC 输出网格由 SNAP 产品定义，统一入口的 --resolution 对此后端不生效。",
            ],
        )
