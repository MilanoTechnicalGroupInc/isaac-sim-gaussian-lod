"""Compare reproducible full-high and Gaussian LOD benchmark reports."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class BenchmarkError(ValueError):
    """Benchmark inputs are incomplete or incomparable."""


def load_benchmark(path: str | Path) -> dict[str, Any]:
    benchmark_path = Path(path)
    try:
        report = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"unable to read benchmark {benchmark_path}: {exc}") from exc
    if report.get("schema") != "mtg.isaac.gaussian_lod.benchmark.v1":
        raise BenchmarkError(f"unsupported benchmark schema: {benchmark_path}")
    if int(report.get("frames", 0)) < 100:
        raise BenchmarkError(f"benchmark must contain at least 100 frames: {benchmark_path}")
    return report


def compare_benchmarks(
    baseline: dict[str, Any],
    lod: dict[str, Any],
    *,
    minimum_speedup: float = 1.25,
    maximum_near_field_rmse: float = 3.0,
) -> dict[str, Any]:
    comparable = ("scene_sha256", "width", "height", "trajectory_sha256")
    mismatches = [key for key in comparable if baseline.get(key) != lod.get(key)]
    if mismatches:
        raise BenchmarkError(f"benchmark inputs differ: {', '.join(mismatches)}")
    baseline_fps = float(baseline["median_fps"])
    lod_fps = float(lod["median_fps"])
    if not all(math.isfinite(value) and value > 0.0 for value in (baseline_fps, lod_fps)):
        raise BenchmarkError("median FPS values must be finite and positive")
    speedup = lod_fps / baseline_fps
    selector_p95_ms = float(lod.get("selector_p95_ms", math.inf))
    near_field_rmse = float(lod.get("near_field_rmse", math.inf))
    gates = {
        "speedup": speedup >= minimum_speedup,
        "selector_p95": selector_p95_ms < 1.0,
        "near_field": near_field_rmse <= maximum_near_field_rmse,
    }
    return {
        "schema": "mtg.isaac.gaussian_lod.benchmark_comparison.v1",
        "baseline_median_fps": baseline_fps,
        "lod_median_fps": lod_fps,
        "speedup": speedup,
        "minimum_speedup": minimum_speedup,
        "selector_p95_ms": selector_p95_ms,
        "near_field_rmse": near_field_rmse,
        "gates": gates,
        "passed": all(gates.values()),
    }
