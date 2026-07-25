#!/usr/bin/env python3
"""Benchmark full-high versus camera-frustum LOD inside Isaac Sim 6.0.1."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--camera", required=True)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--mode", choices=("full-high", "lod"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--reference-image", type=Path)
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--warmup-frames", type=int, default=200)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--gpu-frametime", action="store_true", required=True)
    args = parser.parse_args()
    if args.frames < 100:
        parser.error("--frames must be at least 100")
    return args


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def look_at(eye, target):
    from pxr import Gf

    eye = Gf.Vec3d(*eye)
    target = Gf.Vec3d(*target)
    forward = (target - eye).GetNormalized()
    up = Gf.Vec3d(0, 0, 1)
    if abs(forward * up) > 0.99:
        up = Gf.Vec3d(0, 1, 0)
    right = (forward ^ up).GetNormalized()
    camera_up = (right ^ forward).GetNormalized()
    return Gf.Matrix4d(
        right[0],
        right[1],
        right[2],
        0,
        camera_up[0],
        camera_up[1],
        camera_up[2],
        0,
        -forward[0],
        -forward[1],
        -forward[2],
        0,
        eye[0],
        eye[1],
        eye[2],
        1,
    )


def ensure_lights(stage) -> None:
    from pxr import Gf, UsdGeom, UsdLux

    if not stage.GetPrimAtPath("/World/GaussianLodBenchmark/Dome"):
        dome = UsdLux.DomeLight.Define(stage, "/World/GaussianLodBenchmark/Dome")
        dome.GetIntensityAttr().Set(400.0)
    if not stage.GetPrimAtPath("/World/GaussianLodBenchmark/Sun"):
        sun = UsdLux.DistantLight.Define(stage, "/World/GaussianLodBenchmark/Sun")
        sun.GetIntensityAttr().Set(1500.0)
        UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50, 20, 0))


def vram_used_mib() -> float | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        values = [float(line) for line in result.stdout.splitlines() if line.strip()]
        return sum(values)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def image_rmse(reference: Path | None, actual: Path) -> float:
    if reference is None:
        return 0.0
    from PIL import Image

    left = np.asarray(Image.open(reference).convert("RGB"), dtype=np.float32)
    right = np.asarray(Image.open(actual).convert("RGB"), dtype=np.float32)
    if left.shape != right.shape:
        raise ValueError(f"capture shapes differ: {left.shape} versus {right.shape}")
    return float(np.sqrt(np.mean(np.square(left - right))))


async def wait_for_capture(helper) -> None:
    await helper.wait_for_result(completion_frames=30)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "exts" / "mtg.isaac.gaussian_lod"))

    from isaacsim import SimulationApp

    app = SimulationApp(
        {
            "headless": True,
            "width": args.width,
            "height": args.height,
            "renderer": "RayTracedLighting",
        }
    )
    import carb
    import omni.timeline
    import omni.usd
    from mtg_isaac_gaussian_lod.runtime import GaussianLodRuntime
    from omni.kit.viewport.utility import (
        capture_viewport_to_file,
        get_active_viewport,
    )
    from pxr import UsdGeom

    settings = carb.settings.get_settings()
    settings.set("/rtx/rendermode", "RayTracedLighting")
    settings.set("/rtx/post/tonemap/op", 4)
    settings.set("/rtx/post/tonemap/filmIso", 200.0)
    settings.set("/rtx/post/tonemap/enabled", True)
    settings.set("/app/profilerBackend", "tracy")

    stage_path = args.stage.resolve(strict=True)
    trajectory_path = args.trajectory.resolve(strict=True)
    context = omni.usd.get_context()
    if not context.open_stage(str(stage_path)):
        raise RuntimeError(f"failed to open stage: {stage_path}")
    stage = None
    for _ in range(600):
        app.update()
        candidate = context.get_stage()
        if not candidate:
            continue
        root_path = candidate.GetRootLayer().realPath
        if root_path and Path(root_path).resolve() == stage_path:
            stage = candidate
            break
    if stage is None:
        raise RuntimeError(f"stage did not finish opening: {stage_path}")
    stage.SetEditTarget(stage.GetSessionLayer())
    ensure_lights(stage)
    camera_prim = stage.GetPrimAtPath(args.camera)
    if not camera_prim or not camera_prim.IsA(UsdGeom.Camera):
        raise ValueError(f"camera prim not found: {args.camera}")
    camera_xform = UsdGeom.Xformable(camera_prim)
    camera_xform.ClearXformOpOrder()
    camera_op = camera_xform.AddTransformOp()
    viewport = get_active_viewport()
    viewport.camera_path = args.camera

    runtime = GaussianLodRuntime()
    if not runtime.load_from_stage():
        raise RuntimeError(runtime.stats.message)
    runtime.active_camera = args.camera
    runtime.update_interval_s = 0.01
    runtime.begin_warmup()
    while runtime.stats.state == "warmup":
        runtime.update()
        app.update()

    if args.mode == "full-high":
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

    trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
    poses = trajectory.get("poses", [])
    if not poses:
        raise ValueError("trajectory JSON must contain a non-empty poses list")
    timeline = omni.timeline.get_timeline_interface()
    timeline.play()
    for index in range(args.warmup_frames):
        pose = poses[index % len(poses)]
        camera_op.Set(look_at(pose["eye"], pose["target"]))
        runtime.update()
        app.update()

    frame_times_ms: list[float] = []
    selector_times_ms: list[float] = []
    for index in range(args.frames):
        pose = poses[index % len(poses)]
        camera_op.Set(look_at(pose["eye"], pose["target"]))
        started = time.perf_counter()
        runtime.update()
        app.update()
        elapsed = (time.perf_counter() - started) * 1000.0
        frame_times_ms.append(elapsed)
        selector_times_ms.append(runtime.stats.selector_ms if runtime.enabled else 0.0)

    args.capture.parent.mkdir(parents=True, exist_ok=True)
    helper = capture_viewport_to_file(viewport, file_path=str(args.capture.resolve()))
    loop = asyncio.get_event_loop()
    task = loop.create_task(wait_for_capture(helper))
    while not task.done():
        app.update()
        loop.run_until_complete(asyncio.sleep(0))
    task.result()
    timeline.stop()

    values = np.asarray(frame_times_ms, dtype=np.float64)
    fps = 1000.0 / values
    report = {
        "schema": "mtg.isaac.gaussian_lod.benchmark.v1",
        "mode": args.mode,
        "frames": args.frames,
        "width": args.width,
        "height": args.height,
        "scene_sha256": sha256(stage_path),
        "trajectory_sha256": sha256(trajectory_path),
        "median_fps": float(np.median(fps)),
        "p95_frame_ms": float(np.percentile(values, 95)),
        "selector_p95_ms": float(np.percentile(selector_times_ms, 95)),
        "near_field_rmse": image_rmse(args.reference_image, args.capture),
        "capture_path": str(args.capture.resolve()),
        "vram_used_mib": vram_used_mib(),
        "gpu_frametime_requested": args.gpu_frametime,
        "renderer": "RayTracedLighting",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + os.linesep,
        encoding="utf-8",
    )
    app.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
