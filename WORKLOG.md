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
| Delivery validation | `isaac-sim-validator` | Namespace, paths, render mode, and artifact checks |

## Environment

- GPU: NVIDIA GeForce RTX 5090, 32607 MiB
- Target: Isaac Sim 6.0.1 / Kit 110
- Isaac Sim 6.0.1 discovered and validated at
  `D:\isaac-sim-standalone-6.0.1`.
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
- `python -m pytest -q` (28 tests)
- `python -m compileall -q exts scripts tests`
- `python -m build`
- `git diff --check`

MCCD two-tier validation:

- 1,173 resident ParticleField assets across 742 spatial tiles.
- 1,000,000 high plus 100,000 low Gaussians; 10 m tiles.
- All assets warmed successfully in Isaac Sim 6.0.1.
- Real camera smoke capture: 54 high and 40 low tiles visible.
- Vectorized selector: approximately 2 ms on 742 tiles.
- Smooth 960x960 benchmark: 199.4 median LOD FPS versus 189.5 full-high
  (1.052x). This dataset/resolution does not meet the 1.25x release gate.
