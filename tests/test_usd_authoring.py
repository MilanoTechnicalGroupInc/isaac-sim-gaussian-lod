from __future__ import annotations

from pathlib import Path

import pytest
from gaussian_lod_toolkit.models import (
    Aabb,
    Manifest,
    ManifestTier,
    RuntimeConfig,
    TileAsset,
    TileRecord,
)
from gaussian_lod_toolkit.usd_authoring import author_scene_layer, author_tiles_layer

pxr = pytest.importorskip("pxr")
from pxr import Usd, UsdGeom  # noqa: E402


def test_authored_usd_has_resident_invisible_tiers(tmp_path: Path) -> None:
    payload = tmp_path / "high.usda"
    payload.write_text(
        '#usda 1.0\n(\n    defaultPrim = "GaussianSplat"\n)\n\ndef Camera "GaussianSplat" {}\n',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    manifest = Manifest(
        name="fixture",
        tile_size_m=5.0,
        grid_origin_xy=(0.0, 0.0),
        source_to_stage=(
            (1.0, 0.0, 0.0, 2.0),
            (0.0, 1.0, 0.0, 3.0),
            (0.0, 0.0, 1.0, 4.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
        tiers=(ManifestTier("high", 0.0, 20.0, 2.0, "high.ply", "abc", 10, 10),),
        tiles=(
            TileRecord(
                id="tile_0000_0000",
                key=(0, 0),
                bounds=Aabb((0.0, 0.0, -1.0), (5.0, 5.0, 1.0)),
                assets=(TileAsset("high", "high.usda", 10, "def", 100),),
            ),
        ),
        runtime=RuntimeConfig(warmup_batch_size=4),
    )
    tiles_path = tmp_path / "tiles.usda"
    scene_path = tmp_path / "fixture.usda"

    author_tiles_layer(tiles_path, manifest, manifest_path)
    author_scene_layer(scene_path, tiles_path)

    stage = Usd.Stage.Open(str(scene_path))
    root = stage.GetPrimAtPath("/World/GaussianLOD")
    tier = stage.GetPrimAtPath("/World/GaussianLOD/Content/tile_0000_0000/Tier_high")
    content = stage.GetPrimAtPath("/World/GaussianLOD/Content")
    assert root.GetAttribute("mtg:gaussianLod:allResident").Get() is True
    assert root.GetAttribute("mtg:gaussianLod:warmupBatchSize").Get() == 4
    assert UsdGeom.Imageable(tier).ComputeVisibility() == UsdGeom.Tokens.invisible
    assert tier.HasPayload()
    assert tier.IsA(UsdGeom.Camera)
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    transform = UsdGeom.Xformable(content).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    assert tuple(transform.ExtractTranslation()) == pytest.approx((2.0, 3.0, 4.0))
