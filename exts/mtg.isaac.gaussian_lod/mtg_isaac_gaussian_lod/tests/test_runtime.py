from __future__ import annotations

import math

import omni.kit.test
import omni.usd
from gaussian_lod_toolkit.models import (
    Aabb,
    Manifest,
    ManifestTier,
    RuntimeConfig,
    TileAsset,
    TileRecord,
)
from gaussian_lod_toolkit.selector import TileDecision
from pxr import Gf, UsdGeom

from mtg_isaac_gaussian_lod.runtime import GaussianLodRuntime


class TestGaussianLodRuntime(omni.kit.test.AsyncTestCase):
    async def setUp(self) -> None:
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(self.stage, 1.0)
        UsdGeom.Xform.Define(self.stage, "/World")

    async def tearDown(self) -> None:
        await omni.usd.get_context().close_stage_async()

    async def test_camera_adapter_uses_usd_minus_z_forward(self) -> None:
        camera = UsdGeom.Camera.Define(self.stage, "/World/Camera")
        camera.GetFocalLengthAttr().Set(20.0)
        camera.GetHorizontalApertureAttr().Set(20.0)
        camera.GetVerticalApertureAttr().Set(10.0)
        camera.GetClippingRangeAttr().Set(Gf.Vec2f(0.1, 100.0))
        state = GaussianLodRuntime().camera_from_prim("/World/Camera")
        self.assertAlmostEqual(state.horizontal_fov_rad, 2.0 * math.atan(0.5))
        self.assertEqual(state.forward, (0.0, 0.0, -1.0))

    async def test_decision_writes_only_one_visible_tier(self) -> None:
        UsdGeom.Xform.Define(self.stage, "/World/GaussianLOD")
        UsdGeom.Xform.Define(self.stage, "/World/GaussianLOD/Content")
        UsdGeom.Xform.Define(self.stage, "/World/GaussianLOD/Content/Tile_0")
        high = UsdGeom.Xform.Define(self.stage, "/World/GaussianLOD/Content/Tile_0/Tier_high")
        low = UsdGeom.Xform.Define(self.stage, "/World/GaussianLOD/Content/Tile_0/Tier_low")
        runtime = GaussianLodRuntime()
        runtime.manifest = Manifest(
            name="fixture",
            tile_size_m=5,
            grid_origin_xy=(0, 0),
            source_to_stage=tuple(tuple(row) for row in Gf.Matrix4d(1.0)),
            tiers=(
                ManifestTier("high", 0, 10, 1, "h", "a" * 64, 1, 1),
                ManifestTier("low", 10, 100, 5, "l", "b" * 64, 1, 1),
            ),
            tiles=(
                TileRecord(
                    "Tile_0",
                    (0, 0),
                    Aabb((0, 0, 0), (1, 1, 1)),
                    (
                        TileAsset("high", "h.usdz", 1, "a" * 64, 1),
                        TileAsset("low", "l.usdz", 1, "b" * 64, 1),
                    ),
                ),
            ),
            runtime=RuntimeConfig(),
        )
        runtime._visible = {"Tile_0": None}
        previous = self.stage.GetEditTarget()
        self.stage.SetEditTarget(self.stage.GetSessionLayer())
        try:
            runtime._apply_decisions(self.stage, [TileDecision("Tile_0", "high", 1.0, "/Camera")])
        finally:
            self.stage.SetEditTarget(previous)
        self.assertEqual(
            UsdGeom.Imageable(high).ComputeVisibility(),
            UsdGeom.Tokens.inherited,
        )
        self.assertEqual(
            UsdGeom.Imageable(low).ComputeVisibility(),
            UsdGeom.Tokens.invisible,
        )
