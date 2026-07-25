# ruff: noqa: F704, F821
"""Author and start a ZED X stereo IPC stream in the active preview stage.

Injected globals:
    camera_root: root prim of the referenced ZED X asset.
    graph_path: destination Action Graph path.
"""

import isaacsim.core.experimental.utils.app as app_utils
import omni.graph.core as og
import omni.timeline
import omni.usd
from pxr import Sdf


async def _setup_stream() -> None:
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("no stage is open")
    if not stage.GetPrimAtPath(camera_root):
        raise RuntimeError(f"ZED camera root does not exist: {camera_root}")

    keys = og.Controller.Keys
    if not stage.GetPrimAtPath(graph_path):
        og.Controller.edit(
            {"graph_path": graph_path, "evaluator_name": "execution"},
            {
                keys.CREATE_NODES: [
                    ("OnTick", "omni.graph.action.OnPlaybackTick"),
                    ("ZED", "sl.sensor.camera.ZED_Camera"),
                ],
                keys.SET_VALUES: [
                    ("ZED.inputs:cameraModel", "ZED_X"),
                    ("ZED.inputs:lensType", "Wide"),
                    ("ZED.inputs:resolution", "SVGA"),
                    ("ZED.inputs:fps", 30),
                    ("ZED.inputs:streamingPort", 30000),
                    ("ZED.inputs:transportLayerMode", "IPC"),
                    ("ZED.inputs:streamDepth", False),
                ],
                keys.CONNECT: [
                    ("OnTick.outputs:tick", "ZED.inputs:execIn"),
                ],
            },
        )
        stage.GetPrimAtPath(graph_path + "/ZED").GetRelationship(
            "inputs:cameraPrim"
        ).SetTargets([Sdf.Path(camera_root)])
        omni.usd.get_context().save_stage()

    timeline = omni.timeline.get_timeline_interface()
    timeline.play()
    await app_utils.update_app_async(steps=180)
    print(f"ZED stream graph: {graph_path}")
    print(f"ZED camera root: {camera_root}")
    print("ZED output: stereo RGB, SVGA, 30 Hz, IPC, port 30000")
    print(f"Timeline playing: {timeline.is_playing()}")


await _setup_stream()
