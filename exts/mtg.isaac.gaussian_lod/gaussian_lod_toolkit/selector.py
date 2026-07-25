"""Exclusive N-tier selection for one or more camera frusta."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .geometry import aabb_intersects_frustum, distance_to_aabb, frustum_planes
from .models import CameraState, ManifestTier, TileRecord


@dataclass(frozen=True)
class TileDecision:
    tile_id: str
    tier_id: str | None
    distance_m: float | None
    camera_path: str | None


def _nominal_tier(distance_m: float, tiers: tuple[ManifestTier, ...]) -> int | None:
    for index, tier in enumerate(tiers):
        if tier.near_m <= distance_m <= tier.far_m:
            return index
    return None


def _tier_with_hysteresis(
    distance_m: float,
    tiers: tuple[ManifestTier, ...],
    current_tier_id: str | None,
) -> int | None:
    if current_tier_id is not None:
        for index, tier in enumerate(tiers):
            if tier.id != current_tier_id:
                continue
            if tier.near_m - tier.hysteresis_m <= distance_m <= tier.far_m + tier.hysteresis_m:
                return index
            break
    return _nominal_tier(distance_m, tiers)


def _available_tier(
    desired_index: int | None,
    tiers: tuple[ManifestTier, ...],
    tile: TileRecord,
) -> int | None:
    if desired_index is None:
        return None
    available = {asset.tier_id for asset in tile.assets}
    for index in range(desired_index, len(tiers)):
        if tiers[index].id in available:
            return index
    for index in range(desired_index - 1, -1, -1):
        if tiers[index].id in available:
            return index
    return None


def select_tiles(
    tiles: Iterable[TileRecord],
    tiers: tuple[ManifestTier, ...],
    cameras: Iterable[CameraState],
    *,
    current: Mapping[str, str | None] | None = None,
    fov_margin_deg: float = 0.0,
) -> list[TileDecision]:
    """Select at most one resident tier per tile.

    Multi-camera selection is a union: the highest-quality tier requested by
    any camera wins.
    """

    camera_list = list(cameras)
    current = current or {}
    prepared = [
        (camera, frustum_planes(camera, margin_deg=fov_margin_deg)) for camera in camera_list
    ]
    decisions: list[TileDecision] = []
    for tile in tiles:
        best_index: int | None = None
        best_distance: float | None = None
        best_camera: str | None = None
        for camera, planes in prepared:
            if not aabb_intersects_frustum(tile.bounds, planes):
                continue
            distance = distance_to_aabb(camera.position, tile.bounds)
            desired = _tier_with_hysteresis(distance, tiers, current.get(tile.id))
            desired = _available_tier(desired, tiers, tile)
            if desired is None:
                continue
            if best_index is None or desired < best_index:
                best_index = desired
                best_distance = distance
                best_camera = camera.path
            elif desired == best_index and (best_distance is None or distance < best_distance):
                best_distance = distance
                best_camera = camera.path
        decisions.append(
            TileDecision(
                tile_id=tile.id,
                tier_id=None if best_index is None else tiers[best_index].id,
                distance_m=best_distance,
                camera_path=best_camera,
            )
        )
    return decisions
