"""Manifest statistics and optional package-integrity verification."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import Manifest
from .ply_tiles import sha256_file


def inspect_manifest(
    manifest: Manifest,
    manifest_path: Path,
    *,
    verify_assets: bool = False,
) -> dict[str, Any]:
    per_tier: dict[str, dict[str, int]] = defaultdict(lambda: {"tiles": 0, "points": 0, "bytes": 0})
    missing: list[str] = []
    corrupt: list[str] = []
    for tile in manifest.tiles:
        for asset in tile.assets:
            summary = per_tier[asset.tier_id]
            summary["tiles"] += 1
            summary["points"] += asset.point_count
            summary["bytes"] += asset.bytes
            if verify_assets:
                path = (manifest_path.parent / asset.path).resolve()
                if not path.is_file():
                    missing.append(asset.path)
                elif sha256_file(path) != asset.sha256:
                    corrupt.append(asset.path)
    total_bytes = sum(item["bytes"] for item in per_tier.values())
    return {
        "schema": "mtg.isaac.gaussian_lod.inspection.v1",
        "name": manifest.name,
        "tile_size_m": manifest.tile_size_m,
        "spatial_tiles": len(manifest.tiles),
        "resident_assets": sum(item["tiles"] for item in per_tier.values()),
        "resident_asset_bytes": total_bytes,
        "resident_asset_gib": total_bytes / (1024**3),
        "tiers": dict(per_tier),
        "integrity": {
            "verified": verify_assets,
            "missing": missing,
            "corrupt": corrupt,
            "ok": not missing and not corrupt,
        },
    }
