from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from gaussian_lod_toolkit.ply_tiles import (
    PlyValidationError,
    group_bounds,
    inspect_ply,
    tile_ply,
    validate_alignment,
)

from tests.helpers import write_splat


def test_shared_grid_groups_negative_and_positive_positions(tmp_path: Path) -> None:
    source = tmp_path / "map.ply"
    write_splat(source, [(-0.1, 0, 0), (0.1, 0, 0), (5.1, 0, 0)])
    tiled = tile_ply(source, np.eye(4), np.array([0.0, 0.0]), 5.0, 1)
    assert list(tiled.groups) == [(-1, 0), (0, 0), (1, 0)]


def test_conservative_bounds_include_three_sigma_scale(tmp_path: Path) -> None:
    source = tmp_path / "map.ply"
    write_splat(source, [(1.0, 2.0, 3.0)])
    tiled = tile_ply(source, np.eye(4), np.array([0.0, 0.0]), 5.0, 1)
    bounds = group_bounds(tiled, tiled.groups[(0, 0)])
    assert bounds.minimum == pytest.approx((0.7, 1.7, 2.7))
    assert bounds.maximum == pytest.approx((1.3, 2.3, 3.3))


def test_transform_is_applied_for_tiling(tmp_path: Path) -> None:
    source = tmp_path / "map.ply"
    write_splat(source, [(1.0, 0.0, 0.0)])
    transform = np.eye(4)
    transform[0, 3] = 10.0
    tiled = tile_ply(source, transform, np.array([0.0, 0.0]), 5.0, 1)
    assert list(tiled.groups) == [(2, 0)]


def test_alignment_rejects_unrelated_coordinate_frame(tmp_path: Path) -> None:
    high = tmp_path / "high.ply"
    low = tmp_path / "low.ply"
    write_splat(high, [(0, 0, 0), (10, 10, 1)])
    write_splat(low, [(1000, 1000, 0), (1010, 1010, 1)])
    inspections = [inspect_ply(path, np.eye(4)) for path in (high, low)]
    with pytest.raises(PlyValidationError, match="misaligned"):
        validate_alignment(inspections, 5.0)
