"""Kit/USD adapter and all-resident Gaussian LOD runtime."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import carb
import omni.usd
from gaussian_lod_toolkit.config import ConfigError, load_manifest
from gaussian_lod_toolkit.geometry import camera_changed
from gaussian_lod_toolkit.models import (
    FOV_MARGIN_MAX_DEG,
    FOV_MARGIN_MIN_DEG,
    TIER_DEBUG_PALETTE,
    CameraState,
    Manifest,
    ManifestTier,
)
from gaussian_lod_toolkit.selector import TileDecision, select_tiles
from pxr import Sdf, Usd, UsdGeom

EXTENSION_ID = "mtg.isaac.gaussian_lod"


@dataclass
class RuntimeStats:
    state: str = "idle"
    resident_assets: int = 0
    warmed_assets: int = 0
    visible_tiles: int = 0
    visible_points: int = 0
    selector_ms: float = 0.0
    changed_prims: int = 0
    message: str = ""


class GaussianLodRuntime:
    def __init__(self, root_prim: str = "/World/GaussianLOD") -> None:
        self.root_prim = root_prim
        self.enabled = True
        self.fov_margin_deg: float | None = None
        self.update_interval_s: float | None = None
        self.active_camera = ""
        self.camera_union: list[str] = []
        self.debug_overlay = False
        self.manifest: Manifest | None = None
        self.manifest_path: Path | None = None
        self.stats = RuntimeStats()
        self._last_update = 0.0
        self._visible: dict[str, str | None] = {}
        self._warmup_pending: list[str] = []
        self._warmup_visible: list[str] = []
        self._last_cameras: dict[str, CameraState] = {}
        self._force_reselect = True
        self._callbacks: list[Callable[[RuntimeStats], None]] = []

    def subscribe(self, callback: Callable[[RuntimeStats], None]) -> None:
        self._callbacks.append(callback)

    def _publish(self) -> None:
        for callback in tuple(self._callbacks):
            callback(self.stats)

    def reset(self) -> None:
        self.manifest = None
        self.manifest_path = None
        self._last_update = 0.0
        self._visible.clear()
        self._warmup_pending.clear()
        self._warmup_visible.clear()
        self._last_cameras.clear()
        self._force_reselect = True
        self.stats = RuntimeStats()
        self._publish()

    def load_from_stage(self) -> bool:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            self.stats = RuntimeStats(state="error", message="No USD stage is open")
            self._publish()
            return False
        if abs(float(UsdGeom.GetStageMetersPerUnit(stage)) - 1.0) > 1e-9:
            self.stats = RuntimeStats(
                state="error",
                message="Gaussian LOD packages require a metersPerUnit=1 stage",
            )
            self._publish()
            return False
        root = stage.GetPrimAtPath(self.root_prim)
        if not root:
            self.stats = RuntimeStats(
                state="error",
                message=f"Package root not found: {self.root_prim}",
            )
            self._publish()
            return False
        manifest_attr = root.GetAttribute("mtg:gaussianLod:manifest")
        asset = manifest_attr.Get() if manifest_attr else None
        if not asset:
            self.stats = RuntimeStats(
                state="error",
                message=f"{self.root_prim} has no manifest asset",
            )
            self._publish()
            return False
        resolved = str(getattr(asset, "resolvedPath", "") or "")
        if not resolved:
            root_layer = stage.GetRootLayer()
            resolved = Sdf.ComputeAssetPathRelativeToLayer(root_layer, str(asset.path))
        try:
            self.load_manifest_path(Path(resolved))
        except (ConfigError, OSError, ValueError) as exc:
            self.stats = RuntimeStats(state="error", message=str(exc))
            carb.log_error(f"[{EXTENSION_ID}] {exc}")
            self._publish()
            return False
        return True

    def load_manifest_path(self, path: Path) -> None:
        self.manifest = load_manifest(path)
        self.manifest_path = path.resolve()
        self.fov_margin_deg = self.manifest.runtime.fov_margin_deg
        self.update_interval_s = self.manifest.runtime.update_interval_s
        self._visible = {tile.id: None for tile in self.manifest.tiles}
        self._warmup_pending = [
            f"{self.root_prim}/Content/{tile.id}/Tier_{asset.tier_id}"
            for tile in self.manifest.tiles
            for asset in tile.assets
        ]
        self._warmup_visible.clear()
        self._last_cameras.clear()
        self._force_reselect = True
        self.stats = RuntimeStats(
            state="warmup",
            resident_assets=len(self._warmup_pending),
            message="Ready to register resident Gaussian assets",
        )
        self._publish()

    def set_tier_ranges(self, ranges: dict[str, tuple[float, float, float]]) -> None:
        if self.manifest is None:
            return
        tiers: list[ManifestTier] = []
        previous_far = 0.0
        for index, tier in enumerate(self.manifest.tiers):
            near_m, far_m, hysteresis_m = ranges.get(
                tier.id, (tier.near_m, tier.far_m, tier.hysteresis_m)
            )
            if (
                near_m < 0.0
                or far_m <= near_m
                or hysteresis_m < 0.0
                or (index == 0 and near_m != 0.0)
                or (index and not math.isclose(near_m, previous_far, abs_tol=1e-6))
            ):
                raise ValueError("tier bands must be non-negative, ordered, and contiguous")
            tiers.append(
                replace(
                    tier,
                    near_m=float(near_m),
                    far_m=float(far_m),
                    hysteresis_m=float(hysteresis_m),
                )
            )
            previous_far = far_m
        self.manifest = replace(self.manifest, tiers=tuple(tiers))
        self._force_reselect = True

    def configure(
        self,
        *,
        active_camera: str,
        camera_union: list[str],
        multi_camera_mode: str,
        fov_margin_deg: float,
        update_interval_s: float,
        debug_overlay: bool,
    ) -> None:
        if multi_camera_mode not in {"active", "union"}:
            raise ValueError("multi-camera mode must be 'active' or 'union'")
        self.active_camera = active_camera
        self.camera_union = list(dict.fromkeys(camera_union))
        self.fov_margin_deg = min(
            max(float(fov_margin_deg), FOV_MARGIN_MIN_DEG),
            FOV_MARGIN_MAX_DEG,
        )
        self.update_interval_s = max(0.01, float(update_interval_s))
        self.debug_overlay = bool(debug_overlay)
        if self.manifest is not None:
            self.manifest = replace(
                self.manifest,
                runtime=replace(
                    self.manifest.runtime,
                    multi_camera_mode=multi_camera_mode,
                ),
            )
        self._force_reselect = True

    def begin_warmup(self) -> None:
        if self.manifest is not None and self._warmup_pending:
            self.stats.state = "warmup"
            self.stats.message = "Registering all resident assets"
            self._publish()

    def camera_from_prim(self, path: str) -> CameraState:
        stage = omni.usd.get_context().get_stage()
        prim = stage.GetPrimAtPath(path) if stage else None
        if not prim or not prim.IsA(UsdGeom.Camera):
            raise ValueError(f"not a UsdGeomCamera prim: {path}")
        camera = UsdGeom.Camera(prim)
        projection = camera.GetProjectionAttr().Get()
        if projection != UsdGeom.Tokens.perspective:
            raise ValueError(f"only perspective cameras are supported: {path}")
        transform = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(prim)
        position = transform.ExtractTranslation()
        right = tuple(float(transform[0][index]) for index in range(3))
        up = tuple(float(transform[1][index]) for index in range(3))
        backward = tuple(float(transform[2][index]) for index in range(3))
        focal = float(camera.GetFocalLengthAttr().Get())
        horizontal_aperture = float(camera.GetHorizontalApertureAttr().Get())
        vertical_aperture = float(camera.GetVerticalApertureAttr().Get())
        if focal <= 0.0 or horizontal_aperture <= 0.0 or vertical_aperture <= 0.0:
            raise ValueError(f"camera has invalid focal length/aperture: {path}")
        clipping = camera.GetClippingRangeAttr().Get()
        return CameraState(
            path=path,
            position=tuple(map(float, position)),
            right=right,
            up=up,
            forward=tuple(float(-component) for component in backward),
            horizontal_fov_rad=2.0 * math.atan(horizontal_aperture / (2.0 * focal)),
            vertical_fov_rad=2.0 * math.atan(vertical_aperture / (2.0 * focal)),
            near_m=float(clipping[0]),
            far_m=float(clipping[1]),
        )

    def _set_visible(self, stage, prim_path: str, visible: bool) -> bool:
        prim = stage.GetPrimAtPath(prim_path)
        if not prim:
            return False
        imageable = UsdGeom.Imageable(prim)
        current = imageable.ComputeVisibility(Usd.TimeCode.Default())
        desired = UsdGeom.Tokens.inherited if visible else UsdGeom.Tokens.invisible
        if current == desired:
            return False
        if visible:
            imageable.MakeVisible()
        else:
            imageable.MakeInvisible()
        return True

    def _warmup_step(self, stage) -> bool:
        if self.manifest is None:
            return False
        changed = 0
        if self._warmup_visible:
            for path in self._warmup_visible:
                changed += self._set_visible(stage, path, False)
            self.stats.warmed_assets += len(self._warmup_visible)
            self._warmup_visible.clear()
        if self._warmup_pending:
            batch_size = self.manifest.runtime.warmup_batch_size
            batch = self._warmup_pending[:batch_size]
            del self._warmup_pending[:batch_size]
            for path in batch:
                changed += self._set_visible(stage, path, True)
            self._warmup_visible = batch
            self.stats.changed_prims = changed
            self.stats.message = (
                f"Warm-up {self.stats.warmed_assets}/{self.stats.resident_assets} assets"
            )
            self._publish()
            return True
        self.stats.state = "ready"
        self.stats.message = "All Gaussian assets are resident"
        self.stats.changed_prims = changed
        self._force_reselect = True
        self._publish()
        return changed > 0

    def update(self) -> None:
        if not self.enabled or self.manifest is None:
            return
        now = time.monotonic()
        interval = self.update_interval_s or self.manifest.runtime.update_interval_s
        if now - self._last_update < max(interval, 0.01):
            return
        self._last_update = now
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return
        previous_target = stage.GetEditTarget()
        stage.SetEditTarget(stage.GetSessionLayer())
        try:
            if self.stats.state == "warmup":
                self._warmup_step(stage)
                return
            paths = (
                [self.active_camera]
                if self.manifest.runtime.multi_camera_mode == "active"
                else list(dict.fromkeys([self.active_camera, *self.camera_union]))
            )
            paths = [path for path in paths if path]
            if not paths:
                self.stats.message = "Select at least one perspective camera"
                self._publish()
                return
            try:
                cameras = [self.camera_from_prim(path) for path in paths]
            except ValueError as exc:
                self.stats.state = "error"
                self.stats.message = str(exc)
                self._publish()
                return
            thresholds = self.manifest.runtime
            changed_camera = len(cameras) != len(self._last_cameras) or any(
                camera_changed(
                    self._last_cameras.get(camera.path),
                    camera,
                    translation_threshold_m=thresholds.translation_threshold_m,
                    rotation_threshold_deg=thresholds.rotation_threshold_deg,
                )
                for camera in cameras
            )
            if not self._force_reselect and not changed_camera:
                return
            started = time.perf_counter()
            decisions = select_tiles(
                self.manifest.tiles,
                self.manifest.tiers,
                cameras,
                current=self._visible,
                fov_margin_deg=(
                    self.fov_margin_deg
                    if self.fov_margin_deg is not None
                    else self.manifest.runtime.fov_margin_deg
                ),
                tile_size_m=self.manifest.tile_size_m,
                grid_origin_xy=self.manifest.grid_origin_xy,
            )
            selector_ms = (time.perf_counter() - started) * 1000.0
            changed = self._apply_decisions(stage, decisions)
            self._update_debug_overlay(stage, decisions)
            self._last_cameras = {camera.path: camera for camera in cameras}
            self._force_reselect = False
            self.stats.state = "ready"
            self.stats.selector_ms = selector_ms
            self.stats.changed_prims = changed
            self.stats.visible_tiles = sum(item.tier_id is not None for item in decisions)
            points = {
                (tile.id, asset.tier_id): asset.point_count
                for tile in self.manifest.tiles
                for asset in tile.assets
            }
            self.stats.visible_points = sum(
                points.get((item.tile_id, item.tier_id), 0)
                for item in decisions
                if item.tier_id is not None
            )
            self.stats.message = (
                f"{self.stats.visible_tiles} tiles, "
                f"{self.stats.visible_points:,} splats, "
                f"selector {selector_ms:.3f} ms"
            )
            self._publish()
        finally:
            stage.SetEditTarget(previous_target)

    def _apply_decisions(self, stage, decisions: list[TileDecision]) -> int:
        if self.manifest is None:
            return 0
        changed = 0
        assets_by_tile = {
            tile.id: [asset.tier_id for asset in tile.assets] for tile in self.manifest.tiles
        }
        for decision in decisions:
            previous = self._visible.get(decision.tile_id)
            if previous == decision.tier_id:
                continue
            for tier_id in assets_by_tile[decision.tile_id]:
                path = f"{self.root_prim}/Content/{decision.tile_id}/Tier_{tier_id}"
                changed += self._set_visible(stage, path, tier_id == decision.tier_id)
            self._visible[decision.tile_id] = decision.tier_id
        return changed

    def _update_debug_overlay(self, stage, decisions: list[TileDecision]) -> None:
        debug_path = f"{self.root_prim}_Debug"
        existing = stage.GetPrimAtPath(debug_path)
        if not self.debug_overlay:
            if existing:
                UsdGeom.Imageable(existing).MakeInvisible()
            return
        if self.manifest is None:
            return
        from pxr import Gf, Vt

        selected = {
            decision.tile_id: decision.tier_id
            for decision in decisions
            if decision.tier_id is not None
        }
        tier_index = {tier.id: index for index, tier in enumerate(self.manifest.tiers)}
        palette = tuple(Gf.Vec3f(*rgb) for _name, rgb in TIER_DEBUG_PALETTE)
        starts: list[Gf.Vec3f] = []
        ends: list[Gf.Vec3f] = []
        colors: list[Gf.Vec3f] = []
        for tile in self.manifest.tiles:
            tier_id = selected.get(tile.id)
            if tier_id is None:
                continue
            minimum = tile.bounds.minimum
            maximum = tile.bounds.maximum
            corners = [
                Gf.Vec3f(x, y, z)
                for x in (minimum[0], maximum[0])
                for y in (minimum[1], maximum[1])
                for z in (minimum[2], maximum[2])
            ]
            edges = (
                (0, 1),
                (0, 2),
                (0, 4),
                (1, 3),
                (1, 5),
                (2, 3),
                (2, 6),
                (3, 7),
                (4, 5),
                (4, 6),
                (5, 7),
                (6, 7),
            )
            color = palette[tier_index[tier_id] % len(palette)]
            for start, end in edges:
                starts.append(corners[start])
                ends.append(corners[end])
                colors.append(color)
        curves = UsdGeom.BasisCurves.Define(stage, debug_path)
        points = [point for pair in zip(starts, ends, strict=True) for point in pair]
        curves.CreateTypeAttr(UsdGeom.Tokens.linear)
        curves.CreateCurveVertexCountsAttr(Vt.IntArray([2] * len(starts)))
        curves.CreatePointsAttr(Vt.Vec3fArray(points))
        curves.CreateWidthsAttr(Vt.FloatArray([0.025] * len(points)))
        curves.SetWidthsInterpolation(UsdGeom.Tokens.vertex)
        color_primvar = curves.CreateDisplayColorPrimvar(UsdGeom.Tokens.uniform)
        color_primvar.Set(Vt.Vec3fArray(colors))
        UsdGeom.Imageable(curves.GetPrim()).MakeVisible()
