"""Standard 3DGS PLY inspection and deterministic aligned tiling."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from plyfile import PlyData, PlyElement

from .models import Aabb

REQUIRED_FIELDS = {
    "x",
    "y",
    "z",
    "scale_0",
    "scale_1",
    "scale_2",
    "rot_0",
    "rot_1",
    "rot_2",
    "rot_3",
    "opacity",
    "f_dc_0",
    "f_dc_1",
    "f_dc_2",
}


class PlyValidationError(ValueError):
    """The source is not a supported standard 3DGS PLY."""


@dataclass(frozen=True)
class PlyInspection:
    path: Path
    point_count: int
    fields: tuple[str, ...]
    sha256: str
    robust_bounds: Aabb


@dataclass(frozen=True)
class TiledPly:
    ply: PlyData
    vertices: np.ndarray
    stage_positions: np.ndarray
    stage_radii: np.ndarray
    groups: dict[tuple[int, int], np.ndarray]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vertex_data(path: Path) -> tuple[PlyData, np.ndarray]:
    try:
        ply = PlyData.read(str(path))
    except Exception as exc:
        raise PlyValidationError(f"unable to read PLY {path}: {exc}") from exc
    try:
        vertices = ply["vertex"].data
    except KeyError as exc:
        raise PlyValidationError(f"PLY has no vertex element: {path}") from exc
    names = set(vertices.dtype.names or ())
    missing = sorted(REQUIRED_FIELDS - names)
    if missing:
        raise PlyValidationError(
            f"PLY {path.name} is missing standard 3DGS fields: {', '.join(missing)}"
        )
    if len(vertices) == 0:
        raise PlyValidationError(f"PLY contains no Gaussian vertices: {path}")
    return ply, vertices


def stage_positions(vertices: np.ndarray, transform: np.ndarray) -> np.ndarray:
    source = np.column_stack((vertices["x"], vertices["y"], vertices["z"])).astype(
        np.float64,
        copy=False,
    )
    homogeneous = np.column_stack((source, np.ones(len(source), dtype=np.float64)))
    result = (transform @ homogeneous.T).T[:, :3]
    if not np.isfinite(result).all():
        raise PlyValidationError("transformed Gaussian positions contain NaN or infinity")
    return result


def conservative_stage_radii(vertices: np.ndarray, transform: np.ndarray) -> np.ndarray:
    """Return a conservative three-sigma radius in stage units.

    Standard 3DGS stores logarithmic principal-axis scales. A bounding sphere is
    intentionally used here: it is rotation-independent and cannot false-cull
    a Gaussian ellipsoid at a tile/frustum edge.
    """

    log_scales = np.column_stack(
        (vertices["scale_0"], vertices["scale_1"], vertices["scale_2"])
    ).astype(np.float64, copy=False)
    if not np.isfinite(log_scales).all():
        raise PlyValidationError("Gaussian scale fields contain NaN or infinity")
    log_scales = np.clip(log_scales, -30.0, 30.0)
    source_radius = 3.0 * np.exp(np.max(log_scales, axis=1))
    linear_scale_bound = float(np.linalg.norm(transform[:3, :3], ord=2))
    return source_radius * linear_scale_bound


def robust_bounds(positions: np.ndarray, low: float = 0.001, high: float = 0.999) -> Aabb:
    minimum = np.quantile(positions, low, axis=0)
    maximum = np.quantile(positions, high, axis=0)
    return Aabb(tuple(map(float, minimum)), tuple(map(float, maximum)))


def inspect_ply(path: Path, transform: np.ndarray) -> PlyInspection:
    _, vertices = _vertex_data(path)
    positions = stage_positions(vertices, transform)
    return PlyInspection(
        path=path,
        point_count=len(vertices),
        fields=tuple(vertices.dtype.names or ()),
        sha256=sha256_file(path),
        robust_bounds=robust_bounds(positions),
    )


def validate_alignment(inspections: list[PlyInspection], tile_size_m: float) -> None:
    """Reject tier sources whose robust world coverage is materially different."""

    if not inspections:
        raise PlyValidationError("at least one tier inspection is required")
    reference = inspections[0].robust_bounds
    ref_center = reference.center
    ref_size = reference.extent * 2.0
    ref_diagonal = float(np.linalg.norm(ref_size))
    center_tolerance = max(tile_size_m, ref_diagonal * 0.1)
    for inspection in inspections[1:]:
        bounds = inspection.robust_bounds
        center_delta = float(np.linalg.norm(bounds.center - ref_center))
        size = bounds.extent * 2.0
        nonzero = np.maximum(ref_size, 1e-6)
        ratios = size / nonzero
        meaningful_axes = ref_size > max(ref_diagonal * 1e-6, 1e-6)
        bad_scale = np.any(meaningful_axes & ((ratios < 0.5) | (ratios > 2.0)))
        if center_delta > center_tolerance or bad_scale:
            raise PlyValidationError(
                f"tier {inspection.path.name} appears misaligned: robust-center delta "
                f"{center_delta:.3f} m, size ratios {ratios.round(3).tolist()}"
            )


def shared_grid_origin(reference: PlyInspection, tile_size_m: float) -> np.ndarray:
    minimum = np.asarray(reference.robust_bounds.minimum[:2], dtype=np.float64)
    return np.floor(minimum / tile_size_m) * tile_size_m


def tile_ply(
    path: Path,
    transform: np.ndarray,
    origin_xy: np.ndarray,
    tile_size_m: float,
    min_tile_points: int,
) -> TiledPly:
    ply, vertices = _vertex_data(path)
    positions = stage_positions(vertices, transform)
    radii = conservative_stage_radii(vertices, transform)
    keys = np.floor((positions[:, :2] - origin_xy) / tile_size_m).astype(np.int64)
    groups_list: dict[tuple[int, int], list[int]] = {}
    for index, key in enumerate(keys):
        groups_list.setdefault((int(key[0]), int(key[1])), []).append(index)
    groups = {
        key: np.asarray(indices, dtype=np.int64)
        for key, indices in sorted(groups_list.items())
        if len(indices) >= min_tile_points
    }
    return TiledPly(ply, vertices, positions, radii, groups)


def group_bounds(tiled: TiledPly, indices: np.ndarray) -> Aabb:
    positions = tiled.stage_positions[indices]
    radii = tiled.stage_radii[indices, None]
    minimum = np.min(positions - radii, axis=0)
    maximum = np.max(positions + radii, axis=0)
    return Aabb(tuple(map(float, minimum)), tuple(map(float, maximum)))


def union_bounds(bounds: list[Aabb]) -> Aabb:
    minimum = np.min(np.asarray([item.minimum for item in bounds]), axis=0)
    maximum = np.max(np.asarray([item.maximum for item in bounds]), axis=0)
    return Aabb(tuple(map(float, minimum)), tuple(map(float, maximum)))


def write_group(tiled: TiledPly, indices: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    element = PlyElement.describe(tiled.vertices[indices].copy(), "vertex")
    PlyData(
        [element],
        text=False,
        byte_order="<",
        comments=list(tiled.ply.comments),
        obj_info=list(tiled.ply.obj_info),
    ).write(str(output_path))


def inspection_to_dict(inspection: PlyInspection) -> dict[str, Any]:
    return {
        "path": str(inspection.path),
        "point_count": inspection.point_count,
        "field_count": len(inspection.fields),
        "sha256": inspection.sha256,
        "robust_bounds": inspection.robust_bounds.to_dict(),
    }
