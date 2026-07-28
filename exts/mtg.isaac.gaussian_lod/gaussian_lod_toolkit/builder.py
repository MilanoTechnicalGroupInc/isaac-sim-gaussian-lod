"""Build deterministic, aligned multi-tier Gaussian tile packages."""

from __future__ import annotations

import json
import math
import shutil
import tempfile
from pathlib import Path

from .config import load_build_config
from .converter import convert_tile
from .models import SCHEMA_VERSION, Aabb, Manifest, ManifestTier, TileAsset, TileRecord
from .ply_tiles import (
    group_bounds,
    inspect_ply,
    sha256_file,
    shared_grid_origin,
    tile_ply,
    union_bounds,
    validate_alignment,
    write_group,
)
from .usd_authoring import author_scene_layer, author_tiles_layer


def _tile_id(key: tuple[int, int]) -> str:
    def component(value: int) -> str:
        return f"p{value:05d}" if value >= 0 else f"n{abs(value):05d}"

    return f"Tile_{component(key[0])}_{component(key[1])}"


def _replace_output_directory(staging: Path, output_dir: Path, expected_name: str) -> None:
    """Install staging without replacing a directory that is not one of our packages."""
    if not output_dir.exists():
        staging.rename(output_dir)
        return
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise RuntimeError(f"refusing to replace non-package output path: {output_dir}")

    manifest_path = output_dir / "manifest.json"
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"refusing to replace {output_dir}: it does not contain a valid manifest.json"
        ) from exc
    if not isinstance(existing, dict):
        raise RuntimeError(
            f"refusing to replace {output_dir}: its manifest root is not an object"
        )
    if existing.get("schema") != SCHEMA_VERSION or existing.get("name") != expected_name:
        raise RuntimeError(
            f"refusing to replace {output_dir}: its manifest does not identify "
            f"the {expected_name!r} {SCHEMA_VERSION!r} package"
        )

    backup = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.previous-", dir=output_dir.parent))
    backup.rmdir()
    output_dir.rename(backup)
    try:
        staging.rename(output_dir)
    except Exception:
        backup.rename(output_dir)
        raise
    try:
        shutil.rmtree(backup)
    except OSError as exc:
        raise RuntimeError(
            f"installed {output_dir}, but could not remove the previous package at {backup}"
        ) from exc


def build_package(config_path: str | Path) -> Manifest:
    config = load_build_config(config_path, require_sources=True)
    inspections = [inspect_ply(tier.source, config.source_to_stage) for tier in config.tiers]
    validate_alignment(inspections, config.tile_size_m)
    origin = shared_grid_origin(inspections[0], config.tile_size_m)
    tiled_tiers = [
        tile_ply(
            tier.source,
            config.source_to_stage,
            origin,
            config.tile_size_m,
            config.min_tile_points,
        )
        for tier in config.tiers
    ]
    all_keys = sorted({key for tiled in tiled_tiers for key in tiled.groups})

    output_parent = config.output_dir.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{config.output_dir.name}-", dir=output_parent))
    try:
        assets_by_key: dict[tuple[int, int], list[TileAsset]] = {key: [] for key in all_keys}
        bounds_by_key: dict[tuple[int, int], list[Aabb]] = {key: [] for key in all_keys}
        included_by_tier = {tier.id: 0 for tier in config.tiers}

        for tier, tiled in zip(config.tiers, tiled_tiers, strict=True):
            for key, indices in tiled.groups.items():
                tile_id = _tile_id(key)
                relative = Path("tiles") / tier.id / f"{tile_id}.usdc"
                temporary_ply = staging / "working" / tier.id / f"{tile_id}.ply"
                output_asset = staging / relative
                write_group(tiled, indices, temporary_ply)
                convert_tile(temporary_ply, output_asset, config.converter)
                temporary_ply.unlink()
                included_by_tier[tier.id] += len(indices)
                assets_by_key[key].append(
                    TileAsset(
                        tier_id=tier.id,
                        path=relative.as_posix(),
                        point_count=len(indices),
                        sha256=sha256_file(output_asset),
                        bytes=output_asset.stat().st_size,
                    )
                )
                bounds_by_key[key].append(group_bounds(tiled, indices))

        manifest_tiers = tuple(
            ManifestTier(
                id=tier.id,
                near_m=tier.near_m,
                far_m=tier.far_m,
                hysteresis_m=tier.hysteresis_m,
                source_name=tier.source.name,
                source_sha256=inspection.sha256,
                source_point_count=inspection.point_count,
                included_point_count=included_by_tier[tier.id],
            )
            for tier, inspection in zip(config.tiers, inspections, strict=True)
        )
        records = tuple(
            TileRecord(
                id=_tile_id(key),
                key=key,
                bounds=union_bounds(bounds_by_key[key]),
                assets=tuple(
                    sorted(
                        assets_by_key[key],
                        key=lambda asset: [tier.id for tier in config.tiers].index(asset.tier_id),
                    )
                ),
            )
            for key in all_keys
        )
        manifest = Manifest(
            name=config.name,
            tile_size_m=config.tile_size_m,
            grid_origin_xy=(float(origin[0]), float(origin[1])),
            source_to_stage=tuple(
                tuple(float(value) for value in row) for row in config.source_to_stage
            ),
            tiers=manifest_tiers,
            tiles=records,
            runtime=config.runtime,
        )
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tiles_layer = staging / "tiles.usda"
        author_tiles_layer(tiles_layer, manifest, manifest_path)
        author_scene_layer(staging / f"{config.name}.usda", tiles_layer)

        working = staging / "working"
        if working.exists():
            shutil.rmtree(working)
        _replace_output_directory(staging, config.output_dir, config.name)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def estimate_tile_counts(
    config_path: str | Path, tile_size_m: float | None = None
) -> dict[str, object]:
    config = load_build_config(config_path, require_sources=True)
    selected_tile_size = config.tile_size_m if tile_size_m is None else float(tile_size_m)
    if not math.isfinite(selected_tile_size) or selected_tile_size <= 0.0:
        raise ValueError("tile_size_m must be a finite number greater than zero")
    inspections = [inspect_ply(tier.source, config.source_to_stage) for tier in config.tiers]
    validate_alignment(inspections, selected_tile_size)
    origin = shared_grid_origin(inspections[0], selected_tile_size)
    summaries: list[dict[str, object]] = []
    for tier in config.tiers:
        tiled = tile_ply(
            tier.source,
            config.source_to_stage,
            origin,
            selected_tile_size,
            config.min_tile_points,
        )
        included = sum(len(indices) for indices in tiled.groups.values())
        summaries.append(
            {
                "id": tier.id,
                "source": str(tier.source),
                "points": len(tiled.vertices),
                "included_points": included,
                "discarded_sparse_points": len(tiled.vertices) - included,
                "tile_count": len(tiled.groups),
            }
        )
    return {
        "schema": "mtg.isaac.gaussian_lod.validation.v1",
        "name": config.name,
        "tile_size_m": selected_tile_size,
        "grid_origin_xy": origin.tolist(),
        "tiers": summaries,
    }
