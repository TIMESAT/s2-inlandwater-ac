import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import __version__
from .backends import BACKENDS
from .errors import RunFailed, WaterACError
from .products import discover_products, inspect_product
from .runner import run_product


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _parameters(values: Sequence[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise argparse.ArgumentTypeError("--set 必须使用 KEY=VALUE：{}".format(item))
        key, value = item.split("=", 1)
        if not key:
            raise argparse.ArgumentTypeError("--set 参数名不能为空")
        result[key] = value
    return result


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--backend", choices=sorted(BACKENDS), default="acolite")
    parser.add_argument("--output", required=True, help="统一输出根目录")
    parser.add_argument("--profile", choices=("inland", "standard"), default="inland")
    parser.add_argument("--resolution", choices=(10, 20, 60), default=20, type=int)
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="传递后端参数；可重复",
    )
    parser.add_argument("--executable", help="覆盖当前后端的可执行文件/解释器")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不创建输出")
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许写入已有输出目录；不会删除旧文件",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s2-water-ac",
        description="统一调用 Sentinel-2 内陆水体大气校正处理器",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backends = subparsers.add_parser("backends", help="列出支持的后端")
    backends.add_argument("--json", action="store_true")

    doctor = subparsers.add_parser("doctor", help="检查外部处理器是否可用")
    doctor.add_argument("--backend", choices=sorted(BACKENDS))
    doctor.add_argument("--executable", help="检查指定可执行文件")
    doctor.add_argument("--json", action="store_true")

    inspect = subparsers.add_parser("inspect", help="校验并查看一个 L1C 产品")
    inspect.add_argument("input")
    inspect.add_argument("--json", action="store_true")

    run = subparsers.add_parser("run", help="处理单个 SAFE/SAFE.zip")
    run.add_argument("input")
    _add_run_options(run)

    batch = subparsers.add_parser("batch", help="发现并批量处理目录中的 L1C 产品")
    batch.add_argument("input_directory")
    _add_run_options(batch)
    batch.add_argument("--fail-fast", action="store_true")
    return parser


def _cmd_backends(args: argparse.Namespace) -> int:
    data = [
        {
            "name": backend.name,
            "summary": backend.summary,
            "water_specific": backend.water_specific,
        }
        for backend in BACKENDS.values()
    ]
    if args.json:
        print(_json(data))
    else:
        for item in data:
            marker = "水体专用" if item["water_specific"] else "通用基线"
            print("{:<9} {:<8} {}".format(item["name"], marker, item["summary"]))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    names = [args.backend] if args.backend else list(BACKENDS)
    if args.executable and len(names) != 1:
        raise WaterACError("--executable 必须与 --backend 一起使用")
    statuses = [BACKENDS[name].doctor(args.executable).to_dict() for name in names]
    if args.json:
        print(_json(statuses))
    else:
        for status in statuses:
            marker = "OK" if status["available"] else "MISSING"
            path = " ({})".format(status["executable"]) if status["executable"] else ""
            print("{:<7} {:<9} {}{}".format(marker, status["name"], status["detail"], path))
    return 0 if all(item["available"] for item in statuses) else 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    data = inspect_product(args.input).to_dict()
    if args.json:
        print(_json(data))
    else:
        print("产品:   {}".format(data["product_id"]))
        print("平台:   {}".format(data["platform"]))
        print("时间:   {}".format(data["sensing_time"]))
        print("瓦片:   {}".format(data["tile_id"]))
        print("基线:   N{}".format(data["processing_baseline"]))
        print("Granule: {}；波段: {}".format(data["granules"], ",".join(data["bands"])))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    product = inspect_product(args.input)
    result = run_product(
        product=product,
        backend_name=args.backend,
        output_root=Path(args.output),
        profile=args.profile,
        resolution=args.resolution,
        parameters=_parameters(args.set),
        executable=args.executable,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(_json(result))
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    paths = discover_products(args.input_directory)
    if not paths:
        raise WaterACError("没有发现 .SAFE 或 .SAFE.zip 产品")
    summary: Dict[str, object] = {
        "backend": args.backend,
        "discovered": len(paths),
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "results": [],
    }
    results: List[Dict[str, object]] = summary["results"]  # type: ignore[assignment]
    parameters = _parameters(args.set)
    for index, path in enumerate(paths, start=1):
        print("[{}/{}] {}".format(index, len(paths), path.name), file=sys.stderr)
        try:
            product = inspect_product(str(path))
            result = run_product(
                product=product,
                backend_name=args.backend,
                output_root=Path(args.output),
                profile=args.profile,
                resolution=args.resolution,
                parameters=parameters,
                executable=args.executable,
                dry_run=args.dry_run,
                force=args.force,
            )
            status = str(result.get("status"))
            if status == "skipped":
                summary["skipped"] = int(summary["skipped"]) + 1
            else:
                summary["success"] = int(summary["success"]) + 1
            results.append(result)
        except (WaterACError, OSError) as exc:
            summary["failed"] = int(summary["failed"]) + 1
            results.append({"path": str(path), "status": "failed", "error": str(exc)})
            if args.fail_fast:
                break
    print(_json(summary))
    return 1 if summary["failed"] else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "backends":
            return _cmd_backends(args)
        if args.command == "doctor":
            return _cmd_doctor(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "batch":
            return _cmd_batch(args)
        parser.error("unknown command")
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    except RunFailed as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return exc.returncode if 0 < exc.returncode < 126 else 1
    except (WaterACError, OSError) as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
