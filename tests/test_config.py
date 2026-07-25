from __future__ import annotations

from pathlib import Path

import pytest
from gaussian_lod_toolkit.config import ConfigError, load_build_config


def write_config(path: Path, tiers: str) -> None:
    path.write_text(
        f"""
schema: mtg.isaac.gaussian_lod.v1
name: test_map
output_dir: output
tile_size_m: 5
tiers:
{tiers}
""",
        encoding="utf-8",
    )


def test_loads_arbitrary_contiguous_tier_count(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    write_config(
        path,
        """
  - {id: high, source: high.ply, near_m: 0, far_m: 10, hysteresis_m: 1}
  - {id: low, source: low.ply, near_m: 10, far_m: 100, hysteresis_m: 5}
""",
    )
    config = load_build_config(path, require_sources=False)
    assert [tier.id for tier in config.tiers] == ["high", "low"]
    assert config.output_dir == (tmp_path / "output").resolve()


def test_rejects_gap_between_tiers(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    write_config(
        path,
        """
  - {id: high, source: high.ply, near_m: 0, far_m: 10, hysteresis_m: 1}
  - {id: low, source: low.ply, near_m: 12, far_m: 100, hysteresis_m: 5}
""",
    )
    with pytest.raises(ConfigError, match="contiguous"):
        load_build_config(path, require_sources=False)


def test_rejects_converter_without_placeholders(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
schema: mtg.isaac.gaussian_lod.v1
name: test_map
tiers:
  - {id: high, source: high.ply, near_m: 0, far_m: 10, hysteresis_m: 1}
converter:
  command: [python, converter.py]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="placeholders"):
        load_build_config(path, require_sources=False)


def test_rejects_output_directory_containing_build_config(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
schema: mtg.isaac.gaussian_lod.v1
name: test_map
output_dir: .
tiers:
  - {id: high, source: high.ply, near_m: 0, far_m: 10, hysteresis_m: 1}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="dedicated package directory"):
        load_build_config(path, require_sources=False)
