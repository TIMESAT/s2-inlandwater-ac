import os
import re
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Dict, Iterator, List, Sequence, Tuple

from .errors import InputError
from .models import ProductInfo


PRODUCT_RE = re.compile(
    r"^(?P<platform>S2[ABC])_MSIL1C_"
    r"(?P<sensing>\d{8}T\d{6})_N(?P<baseline>\d{4})_"
    r"R(?P<orbit>\d{3})_T(?P<tile>[0-9A-Z]{5})_.*$"
)
BAND_RE = re.compile(r"_(B(?:0[1-9]|1[0-2]|8A))\.jp2$", re.IGNORECASE)
EXPECTED_BANDS = {
    "B01", "B02", "B03", "B04", "B05", "B06", "B07",
    "B08", "B8A", "B09", "B10", "B11", "B12",
}


def _archive_product_id(path: Path) -> str:
    name = path.name
    if name.lower().endswith(".zip"):
        name = name[:-4]
    return name[:-5] if name.upper().endswith(".SAFE") else name


def _metadata(product_id: str) -> Tuple[str, str, str, str, str]:
    match = PRODUCT_RE.match(product_id)
    if not match:
        raise InputError(
            "无法从产品名解析 Sentinel-2 L1C 元数据：{}".format(product_id)
        )
    groups = match.groupdict()
    return (
        groups["platform"],
        groups["sensing"],
        groups["baseline"],
        groups["orbit"],
        groups["tile"],
    )


def _check_bands(bands: Sequence[str], product_id: str) -> List[str]:
    normalized = sorted(set(item.upper() for item in bands))
    missing = sorted(EXPECTED_BANDS.difference(normalized))
    if missing:
        raise InputError(
            "产品 {} 缺少 L1C 波段：{}".format(product_id, ", ".join(missing))
        )
    return normalized


def _inspect_safe(path: Path) -> Tuple[int, List[str]]:
    required = (path / "MTD_MSIL1C.xml", path / "manifest.safe", path / "GRANULE")
    missing = [str(item.name) for item in required if not item.exists()]
    if missing:
        raise InputError("SAFE 结构不完整，缺少：{}".format(", ".join(missing)))

    granules = [item for item in (path / "GRANULE").iterdir() if item.is_dir()]
    if not granules:
        raise InputError("SAFE 产品中没有 GRANULE")

    bands: List[str] = []
    for granule in granules:
        if not (granule / "MTD_TL.xml").is_file():
            raise InputError("Granule 缺少 MTD_TL.xml：{}".format(granule.name))
        for image in (granule / "IMG_DATA").glob("*.jp2"):
            match = BAND_RE.search(image.name)
            if match:
                bands.append(match.group(1))
    return len(granules), bands


def _safe_zip_names(archive: zipfile.ZipFile) -> List[str]:
    names: List[str] = []
    for info in archive.infolist():
        normalized = info.filename.replace("\\", "/")
        item = PurePosixPath(normalized)
        has_drive = bool(item.parts and ":" in item.parts[0])
        if item.is_absolute() or has_drive or ".." in item.parts:
            raise InputError("ZIP 包含不安全路径：{}".format(info.filename))
        names.append(info.filename.rstrip("/"))
    return names


def _inspect_zip(path: Path) -> Tuple[str, int, List[str]]:
    try:
        with zipfile.ZipFile(str(path)) as archive:
            names = _safe_zip_names(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise InputError("无法读取 ZIP：{}".format(exc)) from exc

    roots = {
        name.split("/", 1)[0]
        for name in names
        if "/" in name and name.split("/", 1)[0].upper().endswith(".SAFE")
    }
    roots_with_metadata = {
        root for root in roots if "{}/MTD_MSIL1C.xml".format(root) in names
    }
    if len(roots_with_metadata) != 1:
        raise InputError("ZIP 中必须恰好包含一个完整的 .SAFE 产品")
    root = next(iter(roots_with_metadata))
    if "{}/manifest.safe".format(root) not in names:
        raise InputError("ZIP 内 SAFE 缺少 manifest.safe")

    granule_markers = {
        name.rsplit("/", 1)[0]
        for name in names
        if name.startswith(root + "/GRANULE/") and name.endswith("/MTD_TL.xml")
    }
    if not granule_markers:
        raise InputError("ZIP 内 SAFE 没有有效 GRANULE")
    bands = []
    for name in names:
        if name.startswith(root + "/GRANULE/") and "/IMG_DATA/" in name:
            match = BAND_RE.search(name)
            if match:
                bands.append(match.group(1))
    return root, len(granule_markers), bands


def inspect_product(value: str) -> ProductInfo:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise InputError("输入不存在：{}".format(path))

    archive = path.is_file() and path.name.lower().endswith(".safe.zip")
    if path.is_dir() and path.name.upper().endswith(".SAFE"):
        product_id = _archive_product_id(path)
        granules, bands = _inspect_safe(path)
    elif archive:
        product_id = _archive_product_id(path)
        archive_root, granules, bands = _inspect_zip(path)
        if _archive_product_id(Path(archive_root)) != product_id:
            raise InputError("ZIP 文件名与内部 SAFE 产品名不一致")
    else:
        raise InputError("仅支持 Sentinel-2 .SAFE 目录或 .SAFE.zip 文件")

    platform, sensing, baseline, orbit, tile = _metadata(product_id)
    return ProductInfo(
        path=path,
        product_id=product_id,
        platform=platform,
        sensing_time=sensing,
        processing_baseline=baseline,
        relative_orbit=orbit,
        tile_id=tile,
        granules=granules,
        bands=_check_bands(bands, product_id),
        archive=archive,
    )


def discover_products(value: str) -> List[Path]:
    root = Path(value).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise InputError("批处理输入目录不存在：{}".format(root))

    candidates: List[Path] = []
    for current, directories, files in os.walk(str(root)):
        current_path = Path(current)
        safe_directories = [
            name for name in directories if name.upper().endswith(".SAFE")
        ]
        candidates.extend(current_path / name for name in safe_directories)
        directories[:] = [name for name in directories if name not in safe_directories]
        candidates.extend(
            current_path / name
            for name in files
            if name.lower().endswith(".safe.zip")
        )

    # Downloader directories commonly contain both an extracted SAFE and its ZIP.
    # Prefer the directory to avoid extracting a second copy at processing time.
    selected: Dict[str, Path] = {}
    for candidate in sorted(candidates, key=lambda item: str(item)):
        key = _archive_product_id(candidate)
        previous = selected.get(key)
        if previous is None or (candidate.is_dir() and not previous.is_dir()):
            selected[key] = candidate
    return sorted(selected.values(), key=lambda item: item.name)


@contextmanager
def materialized_product(product: ProductInfo, require_directory: bool) -> Iterator[Path]:
    if not product.archive or not require_directory:
        yield product.path
        return

    with tempfile.TemporaryDirectory(prefix="s2-water-ac-") as temporary:
        temporary_path = Path(temporary)
        with zipfile.ZipFile(str(product.path)) as archive:
            names = _safe_zip_names(archive)
            archive.extractall(str(temporary_path))
        roots = sorted({name.split("/", 1)[0] for name in names if "/" in name})
        safe_roots = [name for name in roots if name.upper().endswith(".SAFE")]
        if len(safe_roots) != 1:
            raise InputError("ZIP 解压后未找到唯一 SAFE 产品")
        yield temporary_path / safe_roots[0]
