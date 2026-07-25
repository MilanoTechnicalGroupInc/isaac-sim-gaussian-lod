from __future__ import annotations

import math

from gaussian_lod_toolkit.models import (
    Aabb,
    CameraState,
    ManifestTier,
    TileAsset,
    TileRecord,
)
from gaussian_lod_toolkit.selector import select_tiles

TIERS = (
    ManifestTier("high", 0, 20, 2, "h.ply", "a" * 64, 100, 100),
    ManifestTier("medium", 20, 60, 5, "m.ply", "b" * 64, 50, 50),
    ManifestTier("low", 60, 150, 10, "l.ply", "c" * 64, 10, 10),
)


def camera(path: str, position=(0.0, 0.0, 0.0), forward=(1.0, 0.0, 0.0)):
    return CameraState(
        path,
        position,
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
        forward,
        math.radians(90),
        math.radians(60),
        0.01,
        200.0,
    )


def tile(tile_id: str, x: float, assets=("high", "medium", "low")) -> TileRecord:
    return TileRecord(
        tile_id,
        (int(x), 0),
        Aabb((x, -1, -1), (x + 2, 1, 1)),
        tuple(TileAsset(item, f"{item}.usdz", 10, "d" * 64, 100) for item in assets),
    )


def test_exclusive_distance_tiers_and_far_cull() -> None:
    decisions = select_tiles(
        [tile("near", 5), tile("middle", 30), tile("far", 80), tile("gone", 170)],
        TIERS,
        [camera("/A")],
    )
    assert [item.tier_id for item in decisions] == ["high", "medium", "low", None]


def test_hysteresis_preserves_current_tier() -> None:
    target = tile("target", 19)
    current_medium = select_tiles([target], TIERS, [camera("/A")], current={"target": "medium"})
    assert current_medium[0].tier_id == "medium"
    current_high = select_tiles(
        [tile("target", 21)],
        TIERS,
        [camera("/A")],
        current={"target": "high"},
    )
    assert current_high[0].tier_id == "high"


def test_union_chooses_highest_requested_quality() -> None:
    target = tile("target", 40)
    cameras = [camera("/Far"), camera("/Near", position=(30, 0, 0))]
    result = select_tiles([target], tiers=TIERS, cameras=cameras)
    assert result[0].tier_id == "high"
    assert result[0].camera_path == "/Near"


def test_missing_desired_asset_falls_back_without_hole() -> None:
    result = select_tiles(
        [tile("target", 5, assets=("medium", "low"))],
        TIERS,
        [camera("/A")],
    )
    assert result[0].tier_id == "medium"


def test_behind_camera_is_hidden() -> None:
    result = select_tiles([tile("behind", -10)], TIERS, [camera("/A")])
    assert result[0].tier_id is None
