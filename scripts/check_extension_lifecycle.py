#!/usr/bin/env python3
"""Enable and disable the Gaussian LOD extension in a live Kit process."""

from __future__ import annotations

from isaacsim import SimulationApp


def main() -> int:
    app = SimulationApp(
        {
            "headless": True,
            "width": 640,
            "height": 480,
            "renderer": "RayTracedLighting",
        }
    )
    try:
        import omni.kit.app

        manager = omni.kit.app.get_app().get_extension_manager()
        extension_id = "mtg.isaac.gaussian_lod"
        if not manager.set_extension_enabled_immediate(extension_id, True):
            raise RuntimeError(f"failed to enable {extension_id}")
        for _ in range(5):
            app.update()
        if not manager.is_extension_enabled(extension_id):
            raise RuntimeError(f"{extension_id} did not remain enabled")
        if not manager.set_extension_enabled_immediate(extension_id, False):
            raise RuntimeError(f"failed to disable {extension_id}")
        print(f"extension lifecycle passed: {extension_id}")
        return 0
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
