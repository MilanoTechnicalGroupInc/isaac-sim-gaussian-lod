"""Exclusive N-tier selection for one or more camera frusta."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np

from .geometry import frustum_planes
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
    tile_size_m: float | None = None,
    grid_origin_xy: tuple[float, float] | None = None,
) -> list[TileDecision]:
    """Select at most one resident tier per tile.

    Multi-camera selection is a union: the highest-quality tier requested by
    any camera wins.
    """

    tile_list = list(tiles)
    camera_list = list(cameras)
    current = current or {}
    prepared = [
        (camera, frustum_planes(camera, margin_deg=fov_margin_deg)) for camera in camera_list
    ]
    if not tile_list:
        return []
    minimums = np.asarray([tile.bounds.minimum for tile in tile_list], dtype=np.float64)
    maximums = np.asarray([tile.bounds.maximum for tile in tile_list], dtype=np.float64)
    if tile_size_m is not None and grid_origin_xy is not None:
        grid_minimums = np.asarray(
            [
                (
                    grid_origin_xy[0] + tile.key[0] * tile_size_m,
                    grid_origin_xy[1] + tile.key[1] * tile_size_m,
                )
                for tile in tile_list
            ],
            dtype=np.float64,
        )
        grid_maximums = grid_minimums + tile_size_m
    else:
        grid_minimums = minimums[:, :2]
        grid_maximums = maximums[:, :2]
    centers = (minimums + maximums) * 0.5
    extents = (maximums - minimums) * 0.5
    best_indices: list[int | None] = [None] * len(tile_list)
    best_distances: list[float | None] = [None] * len(tile_list)
    best_cameras: list[str | None] = [None] * len(tile_list)

    for camera, planes in prepared:
        normals = planes[:, :3]
        signed_centers = centers @ normals.T + planes[:, 3]
        radii = extents @ np.abs(normals).T
        visible_indices = np.flatnonzero(np.all(signed_centers + radii >= 0.0, axis=1))
        position = np.asarray(camera.position[:2], dtype=np.float64)
        delta = np.maximum(
            np.maximum(
                grid_minimums[visible_indices] - position,
                position - grid_maximums[visible_indices],
            ),
            0.0,
        )
        distances = np.linalg.norm(delta, axis=1)
        for tile_index, distance_value in zip(visible_indices, distances, strict=True):
            index = int(tile_index)
            tile = tile_list[index]
            distance = float(distance_value)
            desired = _tier_with_hysteresis(distance, tiers, current.get(tile.id))
            desired = _available_tier(desired, tiers, tile)
            if desired is None:
                continue
            best_index = best_indices[index]
            best_distance = best_distances[index]
            if best_index is None or desired < best_index:
                best_indices[index] = desired
                best_distances[index] = distance
                best_cameras[index] = camera.path
            elif desired == best_index and (best_distance is None or distance < best_distance):
                best_distances[index] = distance
                best_cameras[index] = camera.path

    return [
        TileDecision(
            tile_id=tile.id,
            tier_id=None if best_index is None else tiers[best_index].id,
            distance_m=best_distance,
            camera_path=best_camera,
        )
        for tile, best_index, best_distance, best_camera in zip(
            tile_list,
            best_indices,
            best_distances,
            best_cameras,
            strict=True,
        )
    ]
