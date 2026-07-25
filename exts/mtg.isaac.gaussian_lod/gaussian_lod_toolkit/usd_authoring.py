"""Author the portable USD composition consumed by the Kit extension."""

from __future__ import annotations

from pathlib import Path

from .models import Manifest


def _asset_path(layer_path: Path, target: Path) -> str:
    import os

    return Path(os.path.relpath(target, layer_path.parent)).as_posix()


def author_tiles_layer(path: Path, manifest: Manifest, manifest_path: Path) -> None:
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom
    except ImportError as exc:
        raise RuntimeError(
            "USD authoring requires an Isaac Sim/OpenUSD Python environment"
        ) from exc

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    root = UsdGeom.Xform.Define(stage, "/World/GaussianLOD")
    content = UsdGeom.Xform.Define(stage, "/World/GaussianLOD/Content")

    matrix = Gf.Matrix4d(1.0)
    source_matrix = manifest.source_to_stage
    for row in range(4):
        for column in range(4):
            matrix[row, column] = source_matrix[column][row]
    content.AddTransformOp().Set(matrix)

    root_prim = root.GetPrim()
    attributes = {
        "schema": (Sdf.ValueTypeNames.String, manifest.schema),
        "manifest": (
            Sdf.ValueTypeNames.Asset,
            Sdf.AssetPath(_asset_path(path, manifest_path)),
        ),
        "allResident": (Sdf.ValueTypeNames.Bool, True),
        "warmupBatchSize": (
            Sdf.ValueTypeNames.Int,
            manifest.runtime.warmup_batch_size,
        ),
    }
    for name, (type_name, value) in attributes.items():
        root_prim.CreateAttribute(f"mtg:gaussianLod:{name}", type_name, custom=True).Set(value)

    for tile in manifest.tiles:
        tile_path = f"/World/GaussianLOD/Content/{tile.id}"
        tile_prim = UsdGeom.Xform.Define(stage, tile_path).GetPrim()
        tile_prim.CreateAttribute(
            "mtg:gaussianLod:boundsMin", Sdf.ValueTypeNames.Double3, custom=True
        ).Set(Gf.Vec3d(*tile.bounds.minimum))
        tile_prim.CreateAttribute(
            "mtg:gaussianLod:boundsMax", Sdf.ValueTypeNames.Double3, custom=True
        ).Set(Gf.Vec3d(*tile.bounds.maximum))
        for asset in tile.assets:
            tier_path = f"{tile_path}/Tier_{asset.tier_id}"
            tier_prim = stage.DefinePrim(tier_path)
            tier_prim.CreateAttribute(
                "mtg:gaussianLod:tier", Sdf.ValueTypeNames.Token, custom=True
            ).Set(asset.tier_id)
            tier_prim.GetPayloads().AddPayload(_asset_path(path, path.parent / asset.path))
            UsdGeom.Imageable(tier_prim).MakeInvisible()
    stage.GetRootLayer().Save()


def author_scene_layer(path: Path, tiles_layer: Path) -> None:
    try:
        from pxr import Usd, UsdGeom
    except ImportError as exc:
        raise RuntimeError(
            "USD authoring requires an Isaac Sim/OpenUSD Python environment"
        ) from exc
    stage = Usd.Stage.CreateNew(str(path))
    stage.GetRootLayer().subLayerPaths = [_asset_path(path, tiles_layer)]
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.GetRootLayer().documentation = "Camera-frustum multi-tier Gaussian LOD composition"
    stage.GetRootLayer().Save()
