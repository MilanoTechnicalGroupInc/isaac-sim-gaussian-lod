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
- `ISAAC_SIM_DIR`: not currently set; Kit-native execution is deferred until
  the installation is discoverable.
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
- [ ] Run Isaac Sim integration/render/performance tests when available.
- [x] Distill reusable ParticleField warm-up guidance.
- [x] Publish the private repository:
  `MilanoTechnicalGroupInc/isaac-sim-gaussian-lod`.

## Validation

- `python -m ruff check .`
- `python -m pytest -q` (26 tests)
- `python -m compileall -q exts scripts tests`
- `python -m build`
- `git diff --check`

The packaged Kit test and the 600-frame full-high versus LOD benchmark remain
pending because no Isaac Sim 6.0.1 installation is currently discoverable.
