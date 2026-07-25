"""Perspective frustum and conservative AABB geometry."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np

from .models import Aabb, CameraState


def _unit(value: Iterable[float], label: str) -> np.ndarray:
    vector = np.asarray(tuple(value), dtype=np.float64)
    length = float(np.linalg.norm(vector))
    if not math.isfinite(length) or length < 1e-12:
        raise ValueError(f"{label} must be a finite non-zero vector")
    return vector / length


def normalized_camera(camera: CameraState) -> CameraState:
    """Return an orthonormal camera basis while preserving USD -Z forward semantics."""

    forward = _unit(camera.forward, "camera forward")
    right = _unit(camera.right, "camera right")
    right = _unit(right - forward * np.dot(right, forward), "camera right")
    up = _unit(np.cross(right, forward), "camera up")
    if np.dot(up, np.asarray(camera.up, dtype=np.float64)) < 0.0:
        up = -up
        right = -right
    if not 0.0 < camera.horizontal_fov_rad < math.pi:
        raise ValueError("horizontal FOV must be between 0 and pi")
    if not 0.0 < camera.vertical_fov_rad < math.pi:
        raise ValueError("vertical FOV must be between 0 and pi")
    if camera.near_m < 0.0 or camera.far_m <= camera.near_m:
        raise ValueError("camera clipping range must satisfy 0 <= near < far")
    return CameraState(
        path=camera.path,
        position=tuple(map(float, camera.position)),
        right=tuple(map(float, right)),
        up=tuple(map(float, up)),
        forward=tuple(map(float, forward)),
        horizontal_fov_rad=float(camera.horizontal_fov_rad),
        vertical_fov_rad=float(camera.vertical_fov_rad),
        near_m=float(camera.near_m),
        far_m=float(camera.far_m),
    )


def frustum_planes(camera: CameraState, *, margin_deg: float = 0.0) -> np.ndarray:
    """Return inward-facing planes as rows ``[nx, ny, nz, d]``.

    A point is inside when ``dot(n, point) + d >= 0`` for every plane.
    """

    camera = normalized_camera(camera)
    if margin_deg < 0.0:
        raise ValueError("frustum margin must be non-negative")
    position = np.asarray(camera.position)
    forward = np.asarray(camera.forward)
    right = np.asarray(camera.right)
    up = np.asarray(camera.up)
    margin = math.radians(margin_deg)
    horizontal = min(camera.horizontal_fov_rad * 0.5 + margin, math.pi * 0.499)
    vertical = min(camera.vertical_fov_rad * 0.5 + margin, math.pi * 0.499)

    normals = [
        forward * math.sin(horizontal) + right * math.cos(horizontal),  # left
        forward * math.sin(horizontal) - right * math.cos(horizontal),  # right
        forward * math.sin(vertical) + up * math.cos(vertical),  # bottom
        forward * math.sin(vertical) - up * math.cos(vertical),  # top
        forward,  # near
        -forward,  # far
    ]
    points = [
        position,
        position,
        position,
        position,
        position + forward * camera.near_m,
        position + forward * camera.far_m,
    ]
    planes = np.empty((6, 4), dtype=np.float64)
    for index, (normal, point) in enumerate(zip(normals, points, strict=True)):
        normal = _unit(normal, "frustum plane")
        planes[index, :3] = normal
        planes[index, 3] = -float(np.dot(normal, point))
    return planes


def aabb_intersects_frustum(bounds: Aabb, planes: np.ndarray) -> bool:
    """Conservatively test whether an AABB intersects all frustum half-spaces."""

    center = bounds.center
    extent = bounds.extent
    normals = planes[:, :3]
    signed_center = normals @ center + planes[:, 3]
    radius = np.abs(normals) @ extent
    return bool(np.all(signed_center + radius >= 0.0))


def distance_to_aabb(point: Iterable[float], bounds: Aabb) -> float:
    position = np.asarray(tuple(point), dtype=np.float64)
    minimum = np.asarray(bounds.minimum, dtype=np.float64)
    maximum = np.asarray(bounds.maximum, dtype=np.float64)
    delta = np.maximum(np.maximum(minimum - position, position - maximum), 0.0)
    return float(np.linalg.norm(delta))


def camera_changed(
    previous: CameraState | None,
    current: CameraState,
    *,
    translation_threshold_m: float,
    rotation_threshold_deg: float,
) -> bool:
    if previous is None or previous.path != current.path:
        return True
    translation = float(
        np.linalg.norm(np.asarray(previous.position) - np.asarray(current.position))
    )
    previous_forward = _unit(previous.forward, "previous forward")
    current_forward = _unit(current.forward, "current forward")
    cosine = float(np.clip(np.dot(previous_forward, current_forward), -1.0, 1.0))
    rotation = math.degrees(math.acos(cosine))
    optics_changed = any(
        not math.isclose(left, right, rel_tol=1e-7, abs_tol=1e-9)
        for left, right in (
            (previous.horizontal_fov_rad, current.horizontal_fov_rad),
            (previous.vertical_fov_rad, current.vertical_fov_rad),
            (previous.near_m, current.near_m),
            (previous.far_m, current.far_m),
        )
    )
    return (
        translation >= translation_threshold_m
        or rotation >= rotation_threshold_deg
        or optics_changed
    )
