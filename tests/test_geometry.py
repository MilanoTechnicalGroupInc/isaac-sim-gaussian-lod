from __future__ import annotations

import math

import pytest
from gaussian_lod_toolkit.geometry import (
    aabb_intersects_frustum,
    camera_changed,
    distance_to_aabb,
    frustum_planes,
)
from gaussian_lod_toolkit.models import Aabb, CameraState


def camera(position=(0.0, 0.0, 0.0), forward=(1.0, 0.0, 0.0)) -> CameraState:
    return CameraState(
        path="/Camera",
        position=position,
        right=(0.0, -1.0, 0.0),
        up=(0.0, 0.0, 1.0),
        forward=forward,
        horizontal_fov_rad=math.radians(90.0),
        vertical_fov_rad=math.radians(60.0),
        near_m=0.1,
        far_m=100.0,
    )


def test_frustum_accepts_front_and_rejects_behind_and_side() -> None:
    planes = frustum_planes(camera())
    assert aabb_intersects_frustum(Aabb((9, -1, -1), (11, 1, 1)), planes)
    assert not aabb_intersects_frustum(Aabb((-11, -1, -1), (-9, 1, 1)), planes)
    assert not aabb_intersects_frustum(Aabb((9, 19, -1), (11, 21, 1)), planes)


def test_frustum_margin_keeps_edge_tile() -> None:
    tile = Aabb((10, 11.0, -0.1), (10.5, 11.5, 0.1))
    assert not aabb_intersects_frustum(tile, frustum_planes(camera()))
    assert aabb_intersects_frustum(tile, frustum_planes(camera(), margin_deg=5.0))


def test_negative_frustum_margin_shrinks_selection_cone() -> None:
    tile = Aabb((10, 8.0, -0.1), (10.5, 8.5, 0.1))
    assert aabb_intersects_frustum(tile, frustum_planes(camera()))
    assert not aabb_intersects_frustum(
        tile,
        frustum_planes(camera(), margin_deg=-10.0),
    )


def test_frustum_margin_rejects_values_outside_ui_range() -> None:
    with pytest.raises(ValueError, match="between -30 and 30"):
        frustum_planes(camera(), margin_deg=-30.1)


def test_distance_uses_aabb_surface() -> None:
    bounds = Aabb((5, 5, 5), (10, 10, 10))
    assert distance_to_aabb((7, 7, 7), bounds) == 0.0
    assert distance_to_aabb((2, 7, 7), bounds) == 3.0


def test_camera_change_thresholds_and_optics() -> None:
    previous = camera()
    assert not camera_changed(
        previous,
        camera(position=(0.01, 0, 0)),
        translation_threshold_m=0.05,
        rotation_threshold_deg=1.0,
    )
    assert camera_changed(
        previous,
        camera(position=(0.1, 0, 0)),
        translation_threshold_m=0.05,
        rotation_threshold_deg=1.0,
    )
    changed_optics = CameraState(**{**previous.__dict__, "horizontal_fov_rad": math.radians(80.0)})
    assert camera_changed(
        previous,
        changed_optics,
        translation_threshold_m=1.0,
        rotation_threshold_deg=30.0,
    )
