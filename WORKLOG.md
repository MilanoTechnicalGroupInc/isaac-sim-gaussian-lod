# Worklog

## Goal

Build a standalone Isaac Sim 6.0.1 extension and offline toolkit for aligned,
multi-resolution Gaussian splat tiles with camera-frustum LOD selection.

## Capability map

| Capability | Guidance | Verification |
|---|---|---|
| Isaac Sim extension lifecycle and USD stage integration | `isaac-sim-orchestrator` | Static checks plus packaged Kit tests |
| Perspective camera optics and transforms | `isaac-camera` | Pure geometry tests and Kit camera adapter tests |
| Native Gaussian ParticleField rendering | `isaac-sim-rendering`, NVIDIA GSplat converter | Generated-layer inspection and Kit render test |
| USD composition and relative asset references | `usd-pipeline` | Reopen generated package and inspect references |
| Performance comparison | `profile-isaac-sim` | Deterministic baseline/LOD benchmark report |
| ZED stereo camera rendering and SDK streaming | `isaac-camera`, `profile-isaac-sim` | Paired stereo captures and full-high/LOD frame-time benchmark |
| Interactive GUI preview and live stage setup | `isaac-sim-orchestrator`, `isaac-sim-remote` | Visible Isaac Sim window, open stage, active LOD camera, and viewport validation |
| Delivery validation | `isaac-sim-validator` | Namespace, paths, render mode, and artifact checks |

## Environment

- GPU: NVIDIA GeForce RTX 5090, 32607 MiB
- Target: Isaac Sim 6.0.1 / Kit 110
- Isaac Sim 6.0.1 discovered and validated at
  `D:\isaac-sim-standalone-6.0.1`.
- Stereolabs ZED Isaac Sim 5.2.0 Windows package installed from the official
  release and registered from `D:\zed-isaac-sim-5.2.0`.
- Prototype reference:
  `robotomaton-autonomy:agent/bundle-gather-isaac-usd@aaee5466d8aadd67d2755b257395cf7bb93945d7`

## Checkpoints

- [x] Confirm prototype and target architecture.
- [x] Implement versioned configuration and manifest model.
- [x] Implement PLY validation, aligned tiling, conversion, and USD authoring.
- [x] Implement frustum math and exclusive N-tier selector.
- [x] Implement Isaac Sim UI/runtime adapter and all-resident warm-up.
- [x] Implement inspector, parameter sweep, and benchmark tooling.
- [x] Run pure-Python, OpenUSD, packaging, and static validation.
- [x] Run Isaac Sim integration, render, and performance tests.
- [x] Distill reusable ParticleField warm-up guidance.
- [x] Publish the private repository:
  `MilanoTechnicalGroupInc/isaac-sim-gaussian-lod`.

## Validation

- `python -m ruff check .`
- `python -m pytest -q` (30 tests)
- `python -m compileall -q exts tests` (remote setup scripts intentionally use
  Kit's top-level-await executor)
- `python -m build`
- `git diff --check`

MCCD two-tier validation:

- 1,173 resident ParticleField assets across 742 spatial tiles.
- 1,000,000 high plus 100,000 low Gaussians; 10 m tiles.
- Corrected the MCCD reconstruction conversion after verifying COLMAP camera
  world-up is source `-Y`: Isaac `(X, Y, Z) = (source X, source Z, -source Y)`.
  The earlier opposite X-axis rotation made the Gaussian scene upside down.
- Added a persistent partly-cloudy HDR dome sky to the corrected ZED preview
  and a remote setup tool for applying HDR skies to live stages.
- All assets warmed successfully in Isaac Sim 6.0.1.
- Real camera smoke capture: 54 high and 40 low tiles visible.
- Vectorized selector: approximately 2 ms on 742 tiles.
- Smooth 960x960 benchmark: 199.4 median LOD FPS versus 189.5 full-high
  (1.052x). This dataset/resolution does not meet the 1.25x release gate.
- ZED 5.2.0 Windows IPC, stereo SVGA at 30 Hz: 69.3 median LOD FPS versus
  69.8 full-high; camera target-rate rendering dominates at this size.
- ZED 5.2.0 Windows IPC, stereo HD1080 at 30 Hz: 46.2 median LOD FPS versus
  44.2 full-high. LOD reduced p95 frame time from 27.8 ms to 25.3 ms and
  total reported GPU use from 14,230 MiB to 13,656 MiB.
- Captured left/right ZED images are non-black, correctly oriented, and show
  the expected stereo baseline. HD1080 LOD versus full-high PSNR is 25.71 dB.

MCCD three-tier 5 m validation:

- 5,941 resident ParticleField assets across 2,725 spatial tiles, totaling
  0.84 GiB of generated USDC assets; all asset hashes verified.
- Exclusive tier bands: 2,500,000 ultra Gaussians at 0-5 m, 1,000,000 high
  Gaussians at 5-15 m, and 100,000 low Gaussians at 15-50 m.
- Exact ZED X Wide camera frustum with a 0-degree FOV margin and 5 m tiles.
- All assets warmed successfully in a clean Isaac Sim 6.0.1 process, and ZED
  5.2.0 stereo SVGA IPC streaming initialized without a GPU device loss.
- At the courtyard preview pose, the selector chose 225 tiles / 127,212
  visible splats in 8.64 ms. The interactive GUI snapshot was approximately
  30.7 FPS while ZED stereo streaming; this is not a controlled median
  benchmark and should be compared with the benchmark script before tuning
  release defaults.
- Large builds must run from the configured converter environment to use the
  in-process conversion path. Launching from an unrelated interpreter falls
  back to one converter process per tile and is substantially slower.
