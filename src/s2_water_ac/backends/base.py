import os
import re
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..errors import BackendUnavailable, ConfigurationError
from ..models import BackendStatus, PreparedCommand, ProductInfo


PARAMETER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


def resolve_program(value: str) -> Optional[Path]:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        resolved = candidate.resolve()
        return resolved if resolved.is_file() else None
    found = shutil.which(value)
    return Path(found).resolve() if found else None


def first_existing(candidates: Iterable[Optional[Path]]) -> Optional[Path]:
    for candidate in candidates:
        if candidate is not None and candidate.expanduser().is_file():
            return candidate.expanduser().resolve()
    return None


def validate_parameters(parameters: Dict[str, str]) -> None:
    for key, value in parameters.items():
        if not PARAMETER_RE.fullmatch(key):
            raise ConfigurationError("非法参数名：{}".format(key))
        if "\n" in value or "\r" in value:
            raise ConfigurationError("参数值不能包含换行：{}".format(key))


class Backend(ABC):
    name = ""
    summary = ""
    water_specific = True
    requires_directory = False

    @abstractmethod
    def doctor(self, executable: Optional[str] = None) -> BackendStatus:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    def require_executable(self, executable: Optional[str] = None) -> Path:
        status = self.doctor(executable)
        if not status.available or status.executable is None:
            raise BackendUnavailable("{}：{}".format(self.name, status.detail))
        return status.executable


def env_path(name: str) -> Optional[Path]:
    value = os.environ.get(name)
    return resolve_program(value) if value else None

