#!/usr/bin/env python3
"""Benchmark and capture a streamed ZED stereo pair over a Gaussian LOD stage."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--zed-asset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("full-high", "lod"), required=True)
    parser.add_argument("--resolution", default="SVGA")
    parser.add_argument("--zed-fps", type=int, default=30)
    parser.add_argument("--transport", choices=("IPC", "NETWORK", "BOTH"), default="IPC")
    parser.add_argument("--port", type=int, default=30000)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--warmup-frames", type=int, default=120)
    args = parser.parse_args()
    if args.frames < 100:
        parser.error("--frames must be at least 100")
    return args


def zed_mount_look_at(eye, target, up):
    from pxr import Gf

    eye = Gf.Vec3d(*eye)
    forward = (Gf.Vec3d(*target) - eye).GetNormalized()
    up = Gf.Vec3d(*up).GetNormalized()
    right = (forward ^ up).GetNormalized()
    mount_up = (right ^ forward).GetNormalized()
    # The ZED asset is authored in a robot mounting frame: +X forward, +Z up,
    # and -Y camera-right. Position that frame, not the child USD camera frame.
    return Gf.Matrix4d(
        forward[0],
        forward[1],
        forward[2],
        0,
        -right[0],
        -right[1],
        -right[2],
        0,
        mount_up[0],
        mount_up[1],
        mount_up[2],
        0,
        eye[0],
        eye[1],
        eye[2],
        1,
    )


def ensure_lights(stage) -> None:
    from pxr import Gf, UsdGeom, UsdLux

    dome = UsdLux.DomeLight.Define(stage, "/World/ZedGaussianBenchmark/Dome")
    dome.GetIntensityAttr().Set(400.0)
    sun = UsdLux.DistantLight.Define(stage, "/World/ZedGaussianBenchmark/Sun")
    sun.GetIntensityAttr().Set(1500.0)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50, 20, 0))


def vram_used_mib() -> float | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        return sum(float(line) for line in result.stdout.splitlines() if line.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def as_numpy(value) -> np.ndarray:
    if isinstance(value, dict):
        value = value.get("data")
    if hasattr(value, "numpy"):
        value = value.numpy()
    result = np.asarray(value)
    if result.ndim != 3 or result.shape[2] < 3:
        raise ValueError(f"unexpected RGB result shape: {result.shape}")
    return result[:, :, :3].astype(np.uint8, copy=False)


def save_stereo(left: np.ndarray, right: np.ndarray, output_dir: Path) -> None:
    from PIL import Image

    output_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(left).save(output_dir / "zed_left.png")
    Image.fromarray(right).save(output_dir / "zed_right.png")
    pair = np.concatenate((left, right), axis=1)
    Image.fromarray(pair).save(output_dir / "zed_stereo_pair.png")


def set_full_high(runtime, stage) -> None:
    from pxr import UsdGeom

    first_tier = runtime.manifest.tiers[0].id
    previous_target = stage.GetEditTarget()
    stage.SetEditTarget(stage.GetSessionLayer())
    try:
        for tile in runtime.manifest.tiles:
            for asset in tile.assets:
                prim = stage.GetPrimAtPath(
                    f"/World/GaussianLOD/Content/{tile.id}/Tier_{asset.tier_id}"
                )
                if asset.tier_id == first_tier:
                    UsdGeom.Imageable(prim).MakeVisible()
                else:
                    UsdGeom.Imageable(prim).MakeInvisible()
    finally:
        stage.SetEditTarget(previous_target)
    runtime.enabled = False


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "exts" / "mtg.isaac.gaussian_lod"))

    from isaacsim import SimulationApp

    app = SimulationApp(
        {
            "headless": True,
            "width": 640,
            "height": 360,
            "renderer": "RayTracedLighting",
        }
    )
    annotator = None
    timeline = None
    try:
        import carb
        import omni.kit.app
        import omni.timeline
        import omni.usd
        from mtg_isaac_gaussian_lod.runtime import GaussianLodRuntime
        from pxr import Sdf, UsdGeom

        manager = omni.kit.app.get_app().get_extension_manager()
        if not manager.set_extension_enabled_immediate("sl.sensor.camera", True):
            raise RuntimeError("failed to enable sl.sensor.camera")
        for _ in range(10):
            app.update()
        if not manager.is_extension_enabled("sl.sensor.camera"):
            raise RuntimeError("sl.sensor.camera did not remain enabled")
        from sl.sensor.camera.annotators import ZEDAnnotator

        settings = carb.settings.get_settings()
        settings.set("/rtx/rendermode", "RayTracedLighting")
        settings.set("/rtx/post/tonemap/op", 4)
        settings.set("/rtx/post/tonemap/filmIso", 200.0)
        settings.set("/rtx/post/tonemap/enabled", True)
        settings.set("/app/runLoops/main/rateLimitEnabled", False)

        stage_path = args.stage.resolve(strict=True)
        zed_asset_path = args.zed_asset.resolve(strict=True)
        context = omni.usd.get_context()
        if not context.open_stage(str(stage_path)):
            raise RuntimeError(f"failed to open stage: {stage_path}")
        stage = None
        for _ in range(600):
            app.update()
            candidate = context.get_stage()
            if candidate and candidate.GetRootLayer().realPath:
                if Path(candidate.GetRootLayer().realPath).resolve() == stage_path:
                    stage = candidate
                    break
        if stage is None:
            raise RuntimeError(f"stage did not finish opening: {stage_path}")

        stage.SetEditTarget(stage.GetSessionLayer())
        ensure_lights(stage)
        zed_path = "/World/ZedGaussianBenchmark/ZED"
        zed = UsdGeom.Xform.Define(stage, zed_path)
        zed.GetPrim().GetReferences().AddReference(str(zed_asset_path))
        zed_xform = UsdGeom.Xformable(zed.GetPrim())
        zed_xform.ClearXformOpOrder()
        zed_xform.AddTransformOp().Set(
            zed_mount_look_at(
                (-9.3619253668, 0.2236848594, 1.0967596153),
                (-9.7934517685, -0.6783237680, 1.1096204346),
                (0.0060360912, 0.0113690942, 0.9999171512),
            )
        )
        for _ in range(20):
            app.update()

        left_camera = f"{zed_path}/base_link/ZED_X/CameraLeft"
        right_camera = f"{zed_path}/base_link/ZED_X/CameraRight"
        if not stage.GetPrimAtPath(left_camera) or not stage.GetPrimAtPath(right_camera):
            raise RuntimeError("referenced ZED_X camera prims did not compose")

        runtime = GaussianLodRuntime()
        if not runtime.load_from_stage():
            raise RuntimeError(runtime.stats.message)
        runtime.active_camera = left_camera
        runtime.update_interval_s = 0.01
        runtime.begin_warmup()
        while runtime.stats.state == "warmup":
            runtime.update()
            app.update()
        runtime.update_interval_s = runtime.manifest.runtime.update_interval_s
        first_tier = runtime.manifest.tiers[0].id
        full_high_points = sum(
            asset.point_count
            for tile in runtime.manifest.tiles
            for asset in tile.assets
            if asset.tier_id == first_tier
        )
        if args.mode == "full-high":
            set_full_high(runtime, stage)
        else:
            runtime._last_update = 0.0
            runtime.update()

        annotator = ZEDAnnotator(
            [Sdf.Path(zed_path)],
            camera_model="ZED_X",
            streaming_port=args.port,
            resolution=args.resolution,
            fps=args.zed_fps,
            transport_layer_mode=args.transport,
        )
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        for _ in range(args.warmup_frames):
            runtime.update()
            app.update()

        frame_times_ms: list[float] = []
        selector_times_ms: list[float] = []
        for _ in range(args.frames):
            started = time.perf_counter()
            runtime.update()
            app.update()
            frame_times_ms.append((time.perf_counter() - started) * 1000.0)
            selector_times_ms.append(runtime.stats.selector_ms if runtime.enabled else 0.0)

        left = as_numpy(annotator.left_rgb_annot.get_data())
        right = as_numpy(annotator.right_rgb_annot.get_data())
        save_stereo(left, right, args.output_dir)

        values = np.asarray(frame_times_ms, dtype=np.float64)
        report = {
            "schema": "mtg.isaac.gaussian_lod.zed_benchmark.v1",
            "mode": args.mode,
            "frames": args.frames,
            "median_fps": float(np.median(1000.0 / values)),
            "p50_frame_ms": float(np.percentile(values, 50)),
            "p95_frame_ms": float(np.percentile(values, 95)),
            "p99_frame_ms": float(np.percentile(values, 99)),
            "selector_p95_ms": float(np.percentile(selector_times_ms, 95)),
            "visible_tiles": runtime.stats.visible_tiles if runtime.enabled else None,
            "visible_points": runtime.stats.visible_points if runtime.enabled else full_high_points,
            "visible_by_tier": (
                dict(Counter(tier for tier in runtime._visible.values() if tier is not None))
                if runtime.enabled
                else {first_tier: "all"}
            ),
            "resident_assets": runtime.stats.resident_assets,
            "warmed_assets": runtime.stats.warmed_assets,
            "zed_extension": "5.2.0",
            "zed_model": "ZED_X",
            "zed_resolution": args.resolution,
            "zed_target_fps": args.zed_fps,
            "zed_transport": args.transport,
            "left_camera": left_camera,
            "right_camera": right_camera,
            "left_capture": str((args.output_dir / "zed_left.png").resolve()),
            "right_capture": str((args.output_dir / "zed_right.png").resolve()),
            "stereo_capture": str((args.output_dir / "zed_stereo_pair.png").resolve()),
            "vram_used_mib": vram_used_mib(),
            "renderer": "RayTracedLighting",
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + os.linesep,
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)
        return 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        if timeline is not None:
            timeline.stop()
        if annotator is not None:
            annotator.destroy()
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
