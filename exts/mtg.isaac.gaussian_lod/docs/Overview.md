# Gaussian LOD

This extension loads a generated `mtg.isaac.gaussian_lod.v1` manifest from
`/World/GaussianLOD`, registers every Gaussian tile once, and changes only USD
visibility as selected perspective cameras move.

Open **Window → Gaussian LOD**. Select a `UsdGeomCamera` prim in the Stage and
choose **Use selected camera**. Use **Add selected** when several
simultaneous sensor cameras must contribute to the visible set.

Use the FOV margin slider to tune the selection cone. Negative values shrink
the cone, zero follows the camera optics exactly, and positive values add a
guard band. **Color visible tile outlines by tier** displays a matching
per-tier color legend and visible tile bounds for LOD debugging.

The generated stage and manifest come from the `gaussian-lod build` command in
the repository root.
