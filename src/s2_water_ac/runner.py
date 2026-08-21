import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .backends import get_backend
from .errors import ConfigurationError, RunFailed
from .models import PreparedCommand, ProductInfo
from .products import materialized_product


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: Dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _manifest_base(
    product: ProductInfo,
    backend_name: str,
    output_dir: Path,
    profile: str,
    resolution: int,
    parameters: Dict[str, str],
    prepared: PreparedCommand,
) -> Dict[str, object]:
    manifest: Dict[str, object] = {
        "schema_version": 1,
        "product": product.to_dict(),
        "backend": backend_name,
        "profile": profile,
        "resolution_m": resolution,
        "parameters": parameters,
        "output_directory": str(output_dir),
        "command": prepared.argv,
        "command_display": shlex.join(prepared.argv),
        "expected_outputs": [str(path) for path in prepared.output_paths],
        "expected_output_globs": prepared.output_globs,
        "generated_files": [str(path) for path in prepared.generated_files],
        "notes": prepared.notes,
    }
    if prepared.working_directory is not None:
        manifest["working_directory"] = str(prepared.working_directory)
    return manifest


def _verify_outputs(prepared: PreparedCommand, output_dir: Path) -> List[str]:
    missing = [str(path) for path in prepared.output_paths if not path.exists()]
    for pattern in prepared.output_globs:
        if not any(output_dir.glob(pattern)):
            missing.append("glob:{}".format(pattern))
    return missing


def _execute(prepared: PreparedCommand, output_dir: Path, manifest: Dict[str, object]) -> None:
    log_path = output_dir / "run.log"
    manifest_path = output_dir / "run.json"
    environment = os.environ.copy()
    environment.update(prepared.environment)
    started = time.monotonic()
    manifest.update({"status": "running", "started_at": _now(), "log": str(log_path)})
    _write_json(manifest_path, manifest)

    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                prepared.argv,
                cwd=str(prepared.working_directory or output_dir),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
            )
            assert process.stdout is not None
            with process.stdout:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    sys.stdout.write(line)
                    sys.stdout.flush()
            returncode = process.wait()
    except OSError as exc:
        duration = time.monotonic() - started
        manifest.update(
            {
                "status": "failed",
                "finished_at": _now(),
                "duration_seconds": round(duration, 3),
                "error": str(exc),
            }
        )
        _write_json(manifest_path, manifest)
        raise RunFailed("无法启动外部处理器：{}".format(exc), 126) from exc

    duration = time.monotonic() - started
    if returncode != 0:
        manifest.update(
            {
                "status": "failed",
                "returncode": returncode,
                "finished_at": _now(),
                "duration_seconds": round(duration, 3),
            }
        )
        _write_json(manifest_path, manifest)
        raise RunFailed(
            "外部处理器失败（退出码 {}），日志：{}".format(returncode, log_path),
            returncode,
        )

    missing = _verify_outputs(prepared, output_dir)
    if missing:
        manifest.update(
            {
                "status": "failed",
                "returncode": returncode,
                "finished_at": _now(),
                "duration_seconds": round(duration, 3),
                "error": "处理器退出成功，但未找到预期输出：{}".format(", ".join(missing)),
            }
        )
        _write_json(manifest_path, manifest)
        raise RunFailed(str(manifest["error"]), 3)

    manifest.update(
        {
            "status": "success",
            "returncode": returncode,
            "finished_at": _now(),
            "duration_seconds": round(duration, 3),
        }
    )
    _write_json(manifest_path, manifest)


def run_product(
    product: ProductInfo,
    backend_name: str,
    output_root: Path,
    profile: str = "inland",
    resolution: int = 20,
    parameters: Optional[Dict[str, str]] = None,
    executable: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, object]:
    parameters = dict(parameters or {})
    backend = get_backend(backend_name)
    output_dir = output_root.expanduser().resolve() / product.product_id / backend_name
    manifest_path = output_dir / "run.json"

    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        if manifest_path.is_file():
            try:
                previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                previous = {}
            if previous.get("status") == "success":
                return {
                    "status": "skipped",
                    "product_id": product.product_id,
                    "backend": backend_name,
                    "output_directory": str(output_dir),
                    "reason": "已有成功结果；使用 --force 可重新运行",
                }
        raise ConfigurationError(
            "输出目录非空：{}；确认后使用 --force 重新运行（不会自动删除旧文件）".format(output_dir)
        )

    if dry_run:
        prepared = backend.prepare(
            product,
            product.path,
            output_dir,
            profile,
            resolution,
            parameters,
            executable,
            write_files=False,
        )
        if product.archive and backend.requires_directory:
            prepared.notes.append("实际运行时会先把 ZIP 解压到临时目录，命令中的输入路径将相应替换。")
        plan = _manifest_base(
            product, backend_name, output_dir, profile, resolution, parameters, prepared
        )
        plan["status"] = "dry-run"
        return plan

    output_dir.mkdir(parents=True, exist_ok=True)
    with materialized_product(product, backend.requires_directory) as input_path:
        prepared = backend.prepare(
            product,
            input_path,
            output_dir,
            profile,
            resolution,
            parameters,
            executable,
            write_files=True,
        )
        manifest = _manifest_base(
            product, backend_name, output_dir, profile, resolution, parameters, prepared
        )
        _execute(prepared, output_dir, manifest)
    return manifest
