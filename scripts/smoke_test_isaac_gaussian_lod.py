#!/usr/bin/env python3
"""Render one real camera pose and verify Gaussian LOD runtime behavior."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import traceback
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=960)
    return parser.parse_args()


def look_at(eye, target, up):
    from pxr import Gf

    eye = Gf.Vec3d(*eye)
    forward = (Gf.Vec3d(*target) - eye).GetNormalized()
    up = Gf.Vec3d(*up).GetNormalized()
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
    try:
        import carb
        import omni.usd
        from mtg_isaac_gaussian_lod.runtime import GaussianLodRuntime
        from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
        from pxr import Gf, UsdGeom, UsdLux

        settings = carb.settings.get_settings()
        settings.set("/rtx/rendermode", "RayTracedLighting")
        settings.set("/rtx/post/tonemap/op", 4)
        settings.set("/rtx/post/tonemap/filmIso", 200.0)
        settings.set("/rtx/post/tonemap/enabled", True)

        stage_path = args.stage.resolve(strict=True)
        context = omni.usd.get_context()
        if not context.open_stage(str(stage_path)):
            raise RuntimeError(f"failed to open stage: {stage_path}")
        stage = None
        for _ in range(600):
            app.update()
            candidate = context.get_stage()
            if candidate and Path(candidate.GetRootLayer().realPath).resolve() == stage_path:
                stage = candidate
                break
        if stage is None:
            raise RuntimeError("stage did not finish opening")

        stage.SetEditTarget(stage.GetSessionLayer())
        dome = UsdLux.DomeLight.Define(stage, "/World/GaussianLodSmoke/Dome")
        dome.GetIntensityAttr().Set(400.0)
        sun = UsdLux.DistantLight.Define(stage, "/World/GaussianLodSmoke/Sun")
        sun.GetIntensityAttr().Set(1500.0)
        UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50, 20, 0))

        camera_path = "/World/GaussianLodSmoke/Camera"
        camera = UsdGeom.Camera.Define(stage, camera_path)
        camera.GetHorizontalApertureAttr().Set(20.0)
        camera.GetVerticalApertureAttr().Set(20.0)
        camera.GetFocalLengthAttr().Set(10.0)
        camera.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 150.0))
        transform = look_at(
            (-9.3619253668, 0.2236848594, 1.0967596153),
            (-9.7934517685, -0.6783237680, 1.1096204346),
            (0.0060360912, 0.0113690942, 0.9999171512),
        )
        UsdGeom.Xformable(camera).AddTransformOp().Set(transform)
        viewport = get_active_viewport()
        viewport.camera_path = camera_path

        runtime = GaussianLodRuntime()
        if not runtime.load_from_stage():
            raise RuntimeError(runtime.stats.message)
        runtime.active_camera = camera_path
        runtime.update_interval_s = 0.01
        for _ in range(2000):
            runtime._last_update = 0.0
            runtime.update()
            app.update()
            if runtime.stats.state != "warmup":
                break
        if runtime.stats.state != "ready":
            raise RuntimeError(f"warm-up did not complete: {runtime.stats.message}")

        runtime._last_update = 0.0
        runtime.update()
        for _ in range(100):
            app.update()

        args.output.parent.mkdir(parents=True, exist_ok=True)
        helper = capture_viewport_to_file(viewport, file_path=str(args.output.resolve()))
        loop = asyncio.get_event_loop()
        task = loop.create_task(wait_for_capture(helper))
        while not task.done():
            app.update()
            loop.run_until_complete(asyncio.sleep(0))
        task.result()

        report = {
            "state": runtime.stats.state,
            "resident_assets": runtime.stats.resident_assets,
            "warmed_assets": runtime.stats.warmed_assets,
            "visible_tiles": runtime.stats.visible_tiles,
            "visible_points": runtime.stats.visible_points,
            "visible_by_tier": dict(
                Counter(tier for tier in runtime._visible.values() if tier is not None)
            ),
            "selector_ms": runtime.stats.selector_ms,
            "changed_prims": runtime.stats.changed_prims,
            "vram_used_mib": vram_used_mib(),
            "capture": str(args.output.resolve()),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
