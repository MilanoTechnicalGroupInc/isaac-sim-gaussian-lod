# Isaac Sim Gaussian LOD

[![CI](https://github.com/MilanoTechnicalGroupInc/isaac-sim-gaussian-lod/actions/workflows/validate.yml/badge.svg)](https://github.com/MilanoTechnicalGroupInc/isaac-sim-gaussian-lod/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/MilanoTechnicalGroupInc/isaac-sim-gaussian-lod/blob/main/LICENSE)

`isaac-sim-gaussian-lod` turns aligned high-, medium-, and low-resolution
Gaussian splat PLYs into a shared tile package and renders exactly one quality
tier per visible tile in Isaac Sim 6.0.1.

The extension derives a true perspective frustum from selected `UsdGeomCamera`
prims. Nearby tiles use the highest tier, farther tiles use progressively lower
tiers, and tiles outside every selected frustum are hidden. All tile payloads
are registered once and retained in memory to avoid camera-motion stalls.

> **Project status:** `0.1.x` is an alpha release. The manifest schema is
> versioned, but APIs and installation details may still change before `1.0`.

## Compatibility

| Component | Supported versions |
|---|---|
| Python toolkit | Python 3.10, 3.11, and 3.12 |
| Isaac Sim extension | Isaac Sim 6.0.1 / Kit 110 |
| Renderer | RayTracedLighting |
| Camera model | Perspective pinhole cameras |

The Python wheel contains the offline toolkit and Python modules. A repository
checkout is required for the complete Isaac extension layout, examples,
schemas, and validation scripts.

## Install the toolkit

Clone the repository and install an editable development environment:

```powershell
git clone https://github.com/MilanoTechnicalGroupInc/isaac-sim-gaussian-lod.git
cd isaac-sim-gaussian-lod
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

Configuration files are trusted input: `converter.command` executes the named
program without a shell. Review configuration from third parties before
running `gaussian-lod build`.

## Install the extension

Add this repository's `exts` directory to Isaac Sim's extension search paths,
then enable `mtg.isaac.gaussian_lod` from the Extension Manager. Open
**Window > Gaussian LOD** to select a package and camera prims. The FOV margin
slider ranges from -30 to +30 degrees: negative values tighten the selection
cone inside the physical camera frustum, while positive values expand it.
Enable **Color visible tile outlines by tier** to draw a red/amber/blue/violet
legend and matching bounds around the currently selected tier for each tile.

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

### Output-directory safety

The builder stages a complete package before replacing an existing output.
It will replace a directory only when that directory contains a matching
`mtg.isaac.gaussian_lod.v1` manifest. This prevents a mistaken or untrusted
`output_dir` from deleting an unrelated directory. Keep independent backups
for production datasets and generated assets.

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

## Contributing and security

The project maintainer and code owner is
[@eaturkgeldi-mtg](https://github.com/eaturkgeldi-mtg). See
[CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change. Report security
issues privately as described in [SECURITY.md](SECURITY.md), not in a public
issue.

## License and third-party software

Original project code is licensed under the
[Apache License 2.0](https://github.com/MilanoTechnicalGroupInc/isaac-sim-gaussian-lod/blob/main/LICENSE).
Copyright 2026 Milano Technical Group Inc. Runtime dependencies retain their
own licenses; notably, `plyfile` is GPL-3.0-or-later. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before redistributing a
combined environment.

Isaac Sim and NVIDIA are trademarks or registered trademarks of NVIDIA
Corporation. ZED is a trademark of Stereolabs. This project is not affiliated
with or endorsed by NVIDIA or Stereolabs.
