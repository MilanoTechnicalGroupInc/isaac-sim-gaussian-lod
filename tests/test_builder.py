from __future__ import annotations

import json
from pathlib import Path

import pytest
from gaussian_lod_toolkit import builder

from tests.helpers import write_splat


def test_builder_creates_aligned_multi_tier_manifest(tmp_path: Path, monkeypatch) -> None:
    high = tmp_path / "high.ply"
    low = tmp_path / "low.ply"
    write_splat(high, [(0, 0, 0), (1, 0, 0), (6, 0, 0)])
    write_splat(low, [(0, 0, 0), (6, 0, 0)])
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
schema: mtg.isaac.gaussian_lod.v1
name: fixture
output_dir: {tmp_path.as_posix()}/package
tile_size_m: 5
tiers:
  - {{id: high, source: {high.as_posix()}, near_m: 0, far_m: 10, hysteresis_m: 1}}
  - {{id: low, source: {low.as_posix()}, near_m: 10, far_m: 100, hysteresis_m: 5}}
converter:
  command: [fake, "{{input}}", "{{output}}"]
""",
        encoding="utf-8",
    )

    def fake_convert(_input: Path, output: Path, _config) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-usdz")

    def fake_tiles(path: Path, _manifest, _manifest_path: Path) -> None:
        path.write_text("#usda 1.0\n", encoding="utf-8")

    def fake_scene(path: Path, _tiles_path: Path) -> None:
        path.write_text("#usda 1.0\n", encoding="utf-8")

    monkeypatch.setattr(builder, "convert_tile", fake_convert)
    monkeypatch.setattr(builder, "author_tiles_layer", fake_tiles)
    monkeypatch.setattr(builder, "author_scene_layer", fake_scene)
    manifest = builder.build_package(config)
    assert len(manifest.tiles) == 2
    assert [tier.id for tier in manifest.tiers] == ["high", "low"]
    assert (tmp_path / "package" / "fixture.usda").is_file()
    on_disk = json.loads((tmp_path / "package" / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["tiles"][0]["assets"][0]["tier_id"] == "high"
    assert on_disk["schema"] == "mtg.isaac.gaussian_lod.v1"


def test_estimate_tile_counts_accepts_experimental_tile_size(tmp_path: Path) -> None:
    source = tmp_path / "source.ply"
    write_splat(source, [(0, 0, 0), (4, 0, 0), (6, 0, 0)])
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
schema: mtg.isaac.gaussian_lod.v1
name: sweep
output_dir: {tmp_path.as_posix()}/package
tile_size_m: 5
tiers:
  - {{id: high, source: {source.as_posix()}, near_m: 0, far_m: 100, hysteresis_m: 1}}
""",
        encoding="utf-8",
    )

    default = builder.estimate_tile_counts(config)
    experimental = builder.estimate_tile_counts(config, 10.0)

    assert default["tile_size_m"] == 5.0
    assert experimental["tile_size_m"] == 10.0
    assert default["tiers"][0]["tile_count"] == 2
    assert experimental["tiers"][0]["tile_count"] == 1


def test_replace_output_directory_refuses_unrecognized_directory(tmp_path: Path) -> None:
    output = tmp_path / "package"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("user data\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(RuntimeError, match="does not contain a valid manifest"):
        builder._replace_output_directory(staging, output, "fixture")

    assert marker.read_text(encoding="utf-8") == "user data\n"
    assert staging.is_dir()


def test_replace_output_directory_replaces_matching_package(tmp_path: Path) -> None:
    output = tmp_path / "package"
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps({"schema": "mtg.isaac.gaussian_lod.v1", "name": "fixture"}),
        encoding="utf-8",
    )
    (output / "old.txt").write_text("old\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "new.txt").write_text("new\n", encoding="utf-8")

    builder._replace_output_directory(staging, output, "fixture")

    assert not (output / "old.txt").exists()
    assert (output / "new.txt").read_text(encoding="utf-8") == "new\n"
