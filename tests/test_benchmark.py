from __future__ import annotations

import pytest
from gaussian_lod_toolkit.benchmark import BenchmarkError, compare_benchmarks


def report(fps: float, **overrides):
    value = {
        "schema": "mtg.isaac.gaussian_lod.benchmark.v1",
        "frames": 600,
        "scene_sha256": "a",
        "trajectory_sha256": "b",
        "width": 1920,
        "height": 1080,
        "median_fps": fps,
        "selector_p95_ms": 0.5,
        "near_field_rmse": 2.0,
    }
    value.update(overrides)
    return value


def test_release_gate_passes_at_25_percent_speedup() -> None:
    result = compare_benchmarks(report(40), report(50))
    assert result["speedup"] == pytest.approx(1.25)
    assert result["passed"] is True


def test_release_gate_fails_slow_selector() -> None:
    result = compare_benchmarks(report(40), report(60, selector_p95_ms=1.1))
    assert result["gates"]["selector_p95"] is False
    assert result["passed"] is False


def test_mismatched_trajectory_is_rejected() -> None:
    with pytest.raises(BenchmarkError, match="trajectory_sha256"):
        compare_benchmarks(report(40), report(60, trajectory_sha256="other"))
