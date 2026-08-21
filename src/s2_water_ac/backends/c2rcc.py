import json
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..errors import ConfigurationError
from ..models import BackendStatus, PreparedCommand, ProductInfo
from .base import Backend, env_path, first_existing, resolve_program, validate_parameters


def _coordinate(value: Any, path: Path) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError("ROI 坐标不是数值：{}".format(path))
    number = float(value)
    if not math.isfinite(number):
        raise ConfigurationError("ROI 坐标不是有限数值：{}".format(path))
    return format(number, ".15g")


def _ring_wkt(ring: Any, path: Path) -> str:
    if not isinstance(ring, list) or len(ring) < 4:
        raise ConfigurationError("ROI Polygon 的环至少需要四个坐标：{}".format(path))
    points: List[str] = []
    numeric_points: List[Sequence[Any]] = []
    for point in ring:
        if not isinstance(point, list) or len(point) < 2:
            raise ConfigurationError("ROI 坐标格式无效：{}".format(path))
        numeric_points.append(point)
        points.append(
            "{} {}".format(_coordinate(point[0], path), _coordinate(point[1], path))
        )
    if numeric_points[0][:2] != numeric_points[-1][:2]:
        points.append(points[0])
    return "({})".format(", ".join(points))


def _polygon_wkt_body(coordinates: Any, path: Path) -> str:
    if not isinstance(coordinates, list) or not coordinates:
        raise ConfigurationError("ROI Polygon 没有坐标：{}".format(path))
    return "({})".format(", ".join(_ring_wkt(ring, path) for ring in coordinates))


def _collect_polygons(geometry: Any, path: Path) -> List[Any]:
    if not isinstance(geometry, dict):
        raise ConfigurationError("ROI geometry 格式无效：{}".format(path))
    geometry_type = geometry.get("type")
    if geometry_type == "Polygon":
        return [geometry.get("coordinates")]
    if geometry_type == "MultiPolygon":
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            raise ConfigurationError("ROI MultiPolygon 坐标无效：{}".format(path))
        return list(coordinates)
    if geometry_type == "GeometryCollection":
        geometries = geometry.get("geometries")
        if not isinstance(geometries, list):
            raise ConfigurationError("ROI GeometryCollection 无效：{}".format(path))
        polygons: List[Any] = []
        for item in geometries:
            polygons.extend(_collect_polygons(item, path))
        return polygons
    raise ConfigurationError("ROI 只支持 Polygon/MultiPolygon：{}".format(path))


def _geojson_wkt(path: Path) -> str:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError("无法读取 ROI GeoJSON：{}（{}）".format(path, exc)) from exc
    if not isinstance(document, dict):
        raise ConfigurationError("ROI GeoJSON 顶层格式无效：{}".format(path))

    document_type = document.get("type")
    geometries: List[Any]
    if document_type == "FeatureCollection":
        features = document.get("features")
        if not isinstance(features, list):
            raise ConfigurationError("ROI FeatureCollection 无效：{}".format(path))
        geometries = [
            feature.get("geometry")
            for feature in features
            if isinstance(feature, dict) and feature.get("geometry") is not None
        ]
    elif document_type == "Feature":
        geometries = [document.get("geometry")]
    else:
        geometries = [document]

    polygons: List[Any] = []
    for geometry in geometries:
        polygons.extend(_collect_polygons(geometry, path))
    if not polygons:
        raise ConfigurationError("ROI GeoJSON 中没有 Polygon：{}".format(path))

    bodies = [_polygon_wkt_body(polygon, path) for polygon in polygons]
    if len(bodies) == 1:
        return "POLYGON {}".format(bodies[0])
    return "MULTIPOLYGON ({})".format(", ".join(bodies))


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("true", "1", "yes", "y"):
        return True
    if normalized in ("false", "0", "no", "n"):
        return False
    raise ConfigurationError("{} 必须是 true 或 false".format(name))


def _write_roi_graph(
    path: Path,
    parameters: Dict[str, str],
    geo_region: str,
) -> None:
    graph = ET.Element("graph", {"id": "c2rcc-roi"})
    ET.SubElement(graph, "version").text = "1.0"

    c2rcc = ET.SubElement(graph, "node", {"id": "c2rcc"})
    ET.SubElement(c2rcc, "operator").text = "c2rcc.msi"
    sources = ET.SubElement(c2rcc, "sources")
    ET.SubElement(sources, "sourceProduct").text = "${sourceProduct}"
    processor_parameters = ET.SubElement(c2rcc, "parameters")
    for key, value in parameters.items():
        ET.SubElement(processor_parameters, key).text = value

    subset = ET.SubElement(graph, "node", {"id": "subset-roi"})
    ET.SubElement(subset, "operator").text = "Subset"
    subset_sources = ET.SubElement(subset, "sources")
    ET.SubElement(subset_sources, "sourceProduct", {"refid": "c2rcc"})
    subset_parameters = ET.SubElement(subset, "parameters")
    ET.SubElement(subset_parameters, "geoRegion").text = geo_region
    ET.SubElement(subset_parameters, "copyMetadata").text = "true"

    ET.indent(graph, space="  ")
    path.write_text(
        ET.tostring(graph, encoding="unicode", xml_declaration=True) + "\n",
        encoding="utf-8",
    )


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
        snap_home = os.environ.get("SNAP_HOME")
        resolved = first_existing(
            (
                env_path("SNAP_GPT"),
                Path(snap_home) / "bin" / "gpt" if snap_home else None,
                Path("/Applications/snap/bin/gpt"),
                Path("/Applications/SNAP.app/Contents/MacOS/gpt"),
                home / "Applications/snap/bin/gpt",
                home / "esa-snap/bin/gpt",
                home / "snap/bin/gpt",
                Path("/opt/snap/bin/gpt"),
                Path("/opt/esa-snap/bin/gpt"),
                Path("/usr/local/snap/bin/gpt"),
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
            "已找到 SNAP GPT；可用 gpt -h c2rcc.msi 验证 C2RCC 算子",
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
        del resolution
        validate_parameters(parameters)
        gpt = self.require_executable(executable)
        source = input_path / "MTD_MSIL1C.xml" if input_path.is_dir() else input_path
        target = output_dir / "{}_c2rcc.dim".format(product.product_id)
        processor_parameters = dict(parameters)
        polygon_value = processor_parameters.pop("polygon", None)
        polygon_clip_value = processor_parameters.pop(
            "polygon_clip", "true" if polygon_value else "false"
        )
        polygon_clip = _boolean(polygon_clip_value, "polygon_clip")
        if polygon_clip and not polygon_value:
            raise ConfigurationError("polygon_clip=true 时必须同时设置 polygon")

        defaults = {
            "netSet": "C2X-COMPLEX-Nets" if profile == "inland" else "C2RCC-Nets",
            "outputAsRrs": "true",
            "outputUncertainties": "true",
        }
        defaults.update(processor_parameters)
        generated_files: List[Path] = []
        notes = [
            "inland profile 使用 C2X-COMPLEX-Nets；输出反射率为 Rrs。",
            "C2RCC 输出网格由 SNAP 产品定义，统一入口的 --resolution 对此后端不生效。",
        ]

        if polygon_value and polygon_clip:
            polygon = Path(polygon_value).expanduser().resolve()
            if not polygon.is_file():
                raise ConfigurationError("ROI GeoJSON 不存在：{}".format(polygon))
            geo_region = _geojson_wkt(polygon)
            graph_path = output_dir / "c2rcc-roi.xml"
            if write_files:
                output_dir.mkdir(parents=True, exist_ok=True)
                _write_roi_graph(graph_path, defaults, geo_region)
            argv = [
                str(gpt),
                str(graph_path),
                "-SsourceProduct={}".format(source),
                "-t",
                str(target),
                "-f",
                "BEAM-DIMAP",
            ]
            generated_files.append(graph_path)
            notes.extend(
                [
                    "先对原始 L1C 执行 C2RCC，再使用 polygon 裁到同一 ROI 的外接范围。",
                    "SNAP 原生栅格保持矩形；精确多边形外像元需在标准化/分析阶段用同一 GeoJSON 掩膜。",
                ]
            )
        else:
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
            generated_files=generated_files,
            notes=notes,
        )
