"""Small POLYMER driver exposing MSI options omitted by polymer_cli.py."""

import argparse
from typing import Dict, Optional, Sequence


def _boolean(value: str) -> bool:
    normalized = value.lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise argparse.ArgumentTypeError("expected true/false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="POLYMER Sentinel-2 MSI driver")
    parser.add_argument("input_safe")
    parser.add_argument("output_nc")
    parser.add_argument("--resolution", choices=("10", "20", "60"), default="20")
    parser.add_argument("--ancillary", choices=("embedded", "nasa"), default="embedded")
    parser.add_argument("--multiprocessing", type=int, default=0)
    parser.add_argument("--blocksize", type=int)
    parser.add_argument("--sline", type=int)
    parser.add_argument("--eline", type=int)
    parser.add_argument("--scol", type=int)
    parser.add_argument("--ecol", type=int)
    parser.add_argument("--altitude", type=float)
    parser.add_argument("--use-srf", type=_boolean)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from polymer.level1 import Level1
        from polymer.level2 import Level2
        from polymer.main import run_atm_corr
    except ImportError as exc:
        raise SystemExit("POLYMER import failed: {}".format(exc))

    level1_options: Dict[str, object] = {"resolution": args.resolution}
    if args.ancillary == "embedded":
        level1_options["ancillary"] = "ECMWFT"
    for key in ("blocksize", "sline", "eline", "scol", "ecol", "altitude", "use_srf"):
        value = getattr(args, key)
        if value is not None:
            level1_options[key] = value

    run_atm_corr(
        Level1(args.input_safe, **level1_options),
        Level2(filename=args.output_nc, fmt="netcdf4"),
        multiprocessing=args.multiprocessing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
