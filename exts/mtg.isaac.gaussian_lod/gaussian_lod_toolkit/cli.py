"""Command-line interface for Gaussian LOD package workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .benchmark import BenchmarkError, compare_benchmarks, load_benchmark
from .builder import build_package, estimate_tile_counts
from .config import ConfigError, load_build_config, load_manifest
from .converter import ConversionError
from .inspector import inspect_manifest
from .ply_tiles import PlyValidationError


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gaussian-lod",
        description="Build and inspect camera-frustum Gaussian LOD packages",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate sources and estimate tiles")
    validate.add_argument("config", type=Path)

    build = subparsers.add_parser("build", help="build USDC tiles and a composed USD scene")
    build.add_argument("config", type=Path)

    sweep = subparsers.add_parser("sweep", help="compare tile counts for multiple tile sizes")
    sweep.add_argument("config", type=Path)
    sweep.add_argument(
        "--tile-sizes",
        type=float,
        nargs="+",
        default=[2.5, 5.0, 10.0],
        metavar="METERS",
    )

    inspect = subparsers.add_parser("inspect", help="inspect a generated manifest")
    inspect.add_argument("manifest", type=Path)
    inspect.add_argument("--verify-assets", action="store_true")

    benchmark = subparsers.add_parser("benchmark", help="compare baseline and LOD reports")
    benchmark.add_argument("baseline", type=Path)
    benchmark.add_argument("lod", type=Path)
    benchmark.add_argument("--minimum-speedup", type=float, default=1.25)
    benchmark.add_argument("--maximum-near-field-rmse", type=float, default=3.0)
    benchmark.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            _json(estimate_tile_counts(args.config))
            return 0
        if args.command == "build":
            config = load_build_config(args.config, require_sources=True)
            manifest = build_package(args.config)
            _json(
                {
                    "manifest": str(config.output_dir / "manifest.json"),
                    "spatial_tiles": len(manifest.tiles),
                    "resident_assets": sum(len(tile.assets) for tile in manifest.tiles),
                }
            )
            return 0
        if args.command == "sweep":
            _json(
                {
                    "schema": "mtg.isaac.gaussian_lod.sweep.v1",
                    "profiles": [
                        estimate_tile_counts(args.config, tile_size)
                        for tile_size in args.tile_sizes
                    ],
                }
            )
            return 0
        if args.command == "inspect":
            manifest = load_manifest(args.manifest)
            report = inspect_manifest(
                manifest,
                args.manifest.resolve(),
                verify_assets=args.verify_assets,
            )
            _json(report)
            return 0 if report["integrity"]["ok"] else 2
        if args.command == "benchmark":
            result = compare_benchmarks(
                load_benchmark(args.baseline),
                load_benchmark(args.lod),
                minimum_speedup=args.minimum_speedup,
                maximum_near_field_rmse=args.maximum_near_field_rmse,
            )
            if args.output:
                args.output.write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            _json(result)
            return 0 if result["passed"] else 3
    except (
        BenchmarkError,
        ConfigError,
        ConversionError,
        PlyValidationError,
        RuntimeError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
