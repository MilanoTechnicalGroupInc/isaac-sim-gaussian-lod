# ruff: noqa: F704, F821
"""Open and configure the interactive ZED Gaussian LOD preview in a running Kit app.

Injected globals:
    preview_path: absolute path to the composed preview USDA.
    camera_path: sensor camera prim used by the LOD selector.
    viewport_camera_path: optional proxy camera prim used only by the GUI viewport.
"""

import carb
import isaacsim.core.experimental.utils.app as app_utils
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.kit.viewport.utility import get_active_viewport
from pxr import UsdGeom


async def _setup() -> None:
    context = omni.usd.get_context()
    normalized_path = preview_path.replace("\\", "/")
    carb.settings.get_settings().set("/app/file/ignoreUnsavedStage", True)
    result, error = await context.open_stage_async(
        normalized_path,
        omni.usd.UsdContextInitialLoadSet.LOAD_ALL,
    )
    if not result:
        raise RuntimeError(f"failed to open {normalized_path}: {error}")
    await app_utils.update_app_async(steps=120)

    stage = context.get_stage()
    sensor_camera = stage.GetPrimAtPath(camera_path) if stage else None
    if not sensor_camera or not sensor_camera.IsA(UsdGeom.Camera):
        raise RuntimeError(
            f"preview sensor camera did not compose: {camera_path}; "
            f"stage={context.get_stage_url()}"
        )
    viewer_path = globals().get("viewport_camera_path", camera_path)
    viewer_camera = stage.GetPrimAtPath(viewer_path)
    if not viewer_camera or not viewer_camera.IsA(UsdGeom.Camera):
        raise RuntimeError(f"preview viewport camera did not compose: {viewer_path}")

    extension_id = "mtg.isaac.gaussian_lod"
    settings = carb.settings.get_settings()
    settings.set(f"/exts/{extension_id}/camera", camera_path)
    settings.set(f"/exts/{extension_id}/show_window", True)

    manager = omni.kit.app.get_app().get_extension_manager()
    # Restart an already-enabled extension so it consumes the camera setting
    # written above. This also gives every newly opened stage a clean runtime
    # and warm-up queue.
    if manager.is_extension_enabled(extension_id):
        if not manager.set_extension_enabled_immediate(extension_id, False):
            raise RuntimeError(f"failed to restart {extension_id}")
        await app_utils.update_app_async(steps=2)
    if not manager.set_extension_enabled_immediate(extension_id, True):
        raise RuntimeError(f"failed to enable {extension_id}")

    viewport = get_active_viewport()
    # Never bind the interactive viewport to a referenced sensor camera. Viewport
    # navigation authors transform opinions on its active camera, which can
    # corrupt a sensor rig child after playback begins. The proxy is expendable;
    # the ZED camera remains untouched for streaming and LOD selection.
    viewport.camera_path = viewer_path
    context.get_selection().set_selected_prim_paths([viewer_path], True)
    for window in ui.Workspace.get_windows():
        if window.title == "Gaussian LOD":
            window.visible = True
            break

    # The extension registers every tile payload in small batches before
    # selecting the final camera cone.
    await app_utils.update_app_async(steps=500)

    visible_tiers = []
    for prim in stage.Traverse():
        if "/World/GaussianLOD/Content/" not in prim.GetPath().pathString:
            continue
        if "/Tier_" not in prim.GetPath().pathString:
            continue
        if UsdGeom.Imageable(prim).ComputeVisibility() == UsdGeom.Tokens.inherited:
            visible_tiers.append(prim.GetPath().pathString)

    print(f"Opened preview: {context.get_stage_url()}")
    print(f"Active LOD sensor camera: {camera_path}")
    print(f"Active viewport proxy camera: {viewport.camera_path}")
    print(f"Visible Gaussian tier prims: {len(visible_tiers)}")
    window_visible = any(
        window.title == "Gaussian LOD" and window.visible
        for window in ui.Workspace.get_windows()
    )
    print(f"LOD window visible: {window_visible}")


await _setup()
