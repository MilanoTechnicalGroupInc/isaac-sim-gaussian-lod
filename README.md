# Isaac Sim Gaussian LOD

`isaac-sim-gaussian-lod` turns aligned high-, medium-, and low-resolution
Gaussian splat PLYs into a shared tile package and renders exactly one quality
tier per visible tile in Isaac Sim 6.0.1.

The extension derives a true perspective frustum from selected `UsdGeomCamera`
prims. Nearby tiles use the highest tier, farther tiles use progressively lower
tiers, and tiles outside every selected frustum are hidden. All tile payloads
are registered once and retained in memory to avoid camera-motion stalls.

## Install for tools

```powershell
python -m pip install -e ".[dev]"
gaussian-lod validate examples/three-tier.yaml
gaussian-lod sweep examples/three-tier.yaml --tile-sizes 2.5 5 10
gaussian-lod build examples/three-tier.yaml
gaussian-lod inspect outputs/campus/manifest.json
```

The builder calls NVIDIA's official converter through:

```text
python -m usd_convert_gsplat -i INPUT.ply -o OUTPUT.usdc --up-axis Z
```

Install NVIDIA's `usd-convert-gsplat[usd]` package in a Python 3.11/3.12
environment, or set `converter.command` in the YAML to an equivalent command.
When the configured interpreter is the builder's interpreter, tiles convert
in-process to avoid launching one Python process per tile.

## Install the extension

Add this repository's `exts` directory to Isaac Sim's extension search paths,
then enable `mtg.isaac.gaussian_lod` from the Extension Manager. Open
**Window > Gaussian LOD** to select a package and camera prims.

## Package contract

The source YAML and generated manifest use
`mtg.isaac.gaussian_lod.v1`. All tiers:

- must contain standard 3DGS vertex properties;
- must already share one reconstruction coordinate frame;
- use one explicit source-to-stage transform;
- are split on the same XY grid;
- retain their original spherical-harmonic and opacity data.

Do not assume the COLMAP reconstruction's world-up axis from COLMAP's camera
convention. Derive it from representative camera poses or known gravity, then
transform a known camera center and up vector before building. For a
reconstruction whose world-up is source `-Y`, the Z-up mapping is
`Isaac (X, Y, Z) = source (X, Z, -Y)`.

Frustum culling uses conservative 3D Gaussian bounds. Tier distance uses the
planar tile footprint so unusually large Gaussian scales cannot incorrectly
pull a distant tile into the high-resolution band.

The composed scene is a `.usda` root referencing per-tile `.usdc` assets.
USDC avoids the archive-handle pressure caused by opening hundreds of
independent USDZ payloads. Do not use a `.usdz` as the composition root.

## Benchmark

`gaussian-lod benchmark` compares JSON runs produced by the packaged Isaac
benchmark script. Release validation requires the LOD run to reach at least
`1.25x` the full-high median FPS while keeping near-field captures within the
configured image tolerance.

Run the full-high baseline and then the LOD pass with identical arguments:

```powershell
python scripts/benchmark_isaac_gaussian_lod.py `
  --stage outputs/campus/campus.usda --camera /World/Camera `
  --trajectory examples/trajectory.json --mode full-high `
  --output benchmark-results/full.json --capture benchmark-results/full.png `
  --gpu-frametime

python scripts/benchmark_isaac_gaussian_lod.py `
  --stage outputs/campus/campus.usda --camera /World/Camera `
  --trajectory examples/trajectory.json --mode lod `
  --output benchmark-results/lod.json --capture benchmark-results/lod.png `
  --reference-image benchmark-results/full.png --gpu-frametime

gaussian-lod benchmark benchmark-results/full.json benchmark-results/lod.json
```

### ZED stereo streaming

Use Stereolabs ZED Isaac Sim 5.2.0 or newer with Isaac Sim 6.0.1. Version 5.2
adds Windows IPC streaming and camera target-rate rendering; both materially
reduce the cost of local stereo streaming. The ZED benchmark creates the real
stereo render products, starts SDK streaming, saves both eye images, and records
full-high or LOD frame-time statistics:

```powershell
python scripts/benchmark_zed_gaussian_lod.py `
  --stage outputs/campus/campus.usda `
  --zed-asset D:\zed-isaac-sim-5.2.0\exts\sl.sensor.camera\data\usd\ZED_X.usdc `
  --output-dir benchmark-results/zed-lod `
  --mode lod --resolution HD1080 --zed-fps 30 --transport IPC
```

Run the same command with `--mode full-high` and a different output directory
for a paired baseline. Each output contains `zed_left.png`, `zed_right.png`,
`zed_stereo_pair.png`, and `report.json`.

## Target and limitations

- Isaac Sim 6.0.1 / Kit 110, RayTracedLighting.
- Perspective pinhole cameras only in v1.
- XY tile columns with conservative 3D bounds.
- Frustum and distance culling; geometry occlusion culling is not included.
- Supplied LOD PLYs are tiled but not generated or downsampled.
