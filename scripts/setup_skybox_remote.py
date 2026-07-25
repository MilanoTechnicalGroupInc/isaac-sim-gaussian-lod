# ruff: noqa: F704, F821, I001
"""Apply an HDR sky to a DomeLight in a running Isaac Sim stage.

Injected globals:
    dome_path: DomeLight prim to configure.
    texture_uri: HDR texture URI.
    intensity: optional light intensity, defaults to 400.
    rotation_z: optional sky rotation in degrees, defaults to -20.
"""

import isaacsim.core.experimental.utils.app as app_utils
import omni.usd
from pxr import Gf, Sdf, UsdGeom, UsdLux


stage = omni.usd.get_context().get_stage()
if stage is None:
    raise RuntimeError("no stage is open")

dome = UsdLux.DomeLight(stage.GetPrimAtPath(dome_path))
if not dome:
    dome = UsdLux.DomeLight.Define(stage, dome_path)

dome.GetIntensityAttr().Set(float(globals().get("intensity", 400.0)))
dome.CreateTextureFileAttr().Set(Sdf.AssetPath(texture_uri))
dome.CreateTextureFormatAttr().Set("latlong")

xformable = UsdGeom.Xformable(dome.GetPrim())
rotate_op = next(
    (
        op
        for op in xformable.GetOrderedXformOps()
        if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ
    ),
    None,
)
if rotate_op is None:
    rotate_op = xformable.AddRotateXYZOp()
rotate_op.Set(Gf.Vec3f(0.0, 0.0, float(globals().get("rotation_z", -20.0))))

await app_utils.update_app_async(steps=180)
print(f"HDR skybox: {texture_uri}")
print(f"DomeLight: {dome_path}, intensity={dome.GetIntensityAttr().Get()}")
