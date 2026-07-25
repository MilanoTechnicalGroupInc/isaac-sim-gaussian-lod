# Changelog

## 0.1.0

- Added standard 3DGS PLY validation and deterministic aligned XY tiling.
- Added native ParticleField USDC conversion through NVIDIA's GSplat converter.
- Added portable USD composition and versioned package manifest.
- Added perspective-frustum, exclusive N-tier LOD selection with hysteresis.
- Added active-camera and multi-camera-union modes.
- Added all-resident batched warm-up and session-layer visibility switching.
- Added OmniUI controls, package inspection, and reproducible benchmark gates.
- Switched high-cardinality tile payloads from USDZ archives to USDC crates.
- Preserved payload-supplied ParticleField schema types with untyped host prims.
- Added root-layer units/up-axis metadata and Isaac Sim lifecycle smoke tests.
- Vectorized frustum selection and separated conservative culling bounds from
  planar grid-cell LOD distance.
- Added a live -30 to +30 degree FOV margin slider and tier-colored visible
  tile outline toggle with a dynamic N-tier legend.
