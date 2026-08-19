from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ProductInfo:
    path: Path
    product_id: str
    platform: str
    sensing_time: str
    processing_baseline: str
    relative_orbit: str
    tile_id: str
    granules: int
    bands: List[str]
    archive: bool

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(frozen=True)
class BackendStatus:
    name: str
    available: bool
    executable: Optional[Path]
    detail: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "available": self.available,
            "executable": str(self.executable) if self.executable else None,
            "detail": self.detail,
        }


@dataclass
class PreparedCommand:
    argv: List[str]
    output_paths: List[Path]
    output_globs: List[str] = field(default_factory=list)
    generated_files: List[Path] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
