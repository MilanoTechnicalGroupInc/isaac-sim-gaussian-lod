"""Load and validate build configurations and generated manifests."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from .models import (
    SCHEMA_VERSION,
    BuildConfig,
    ConverterConfig,
    Manifest,
    RuntimeConfig,
    TierConfig,
)

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class ConfigError(ValueError):
    """A user-facing configuration validation failure."""


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a mapping")
    return value


def _positive(value: Any, label: str, *, allow_zero: bool = False) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or (number == 0.0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ConfigError(f"{label} must be a finite {qualifier} number")
    return number


def _resolve(base: Path, value: Any) -> Path:
    path = Path(str(value))
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def load_build_config(path: str | Path, *, require_sources: bool = True) -> BuildConfig:
    import yaml

    config_path = Path(path).resolve()
    try:
        value = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    root = _mapping(value, "configuration")
    if root.get("schema") != SCHEMA_VERSION:
        raise ConfigError(f"schema must be {SCHEMA_VERSION!r}")

    name = str(root.get("name", ""))
    if not _IDENTIFIER.fullmatch(name):
        raise ConfigError("name must start with a letter and contain letters, digits, '_' or '-'")
    base = config_path.parent
    output_dir = _resolve(base, root.get("output_dir", f"outputs/{name}"))
    try:
        config_path.relative_to(output_dir)
    except ValueError:
        pass
    else:
        raise ConfigError(
            "output_dir cannot contain the build configuration; "
            "choose a dedicated package directory"
        )
    tile_size_m = _positive(root.get("tile_size_m", 5.0), "tile_size_m")
    min_tile_points = int(root.get("min_tile_points", 1))
    if min_tile_points < 1:
        raise ConfigError("min_tile_points must be at least 1")

    matrix = np.asarray(root.get("source_to_stage", np.eye(4).tolist()), dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ConfigError("source_to_stage must be a finite 4x4 matrix")
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-9):
        raise ConfigError("source_to_stage must use column-vector affine form with [0,0,0,1] last")
    if abs(np.linalg.det(matrix[:3, :3])) < 1e-12:
        raise ConfigError("source_to_stage linear transform must be invertible")

    tier_values = root.get("tiers")
    if not isinstance(tier_values, list) or not tier_values:
        raise ConfigError("tiers must be a non-empty list")
    tiers: list[TierConfig] = []
    tier_ids: set[str] = set()
    previous_far = 0.0
    for index, raw in enumerate(tier_values):
        tier = _mapping(raw, f"tiers[{index}]")
        tier_id = str(tier.get("id", ""))
        if not _IDENTIFIER.fullmatch(tier_id):
            raise ConfigError(f"tiers[{index}].id is not a valid identifier")
        if tier_id in tier_ids:
            raise ConfigError(f"duplicate tier id: {tier_id}")
        tier_ids.add(tier_id)
        source = _resolve(base, tier.get("source", ""))
        if require_sources and not source.is_file():
            raise ConfigError(f"tier source not found: {source}")
        near_m = _positive(tier.get("near_m", 0.0), f"{tier_id}.near_m", allow_zero=True)
        far_m = _positive(tier.get("far_m"), f"{tier_id}.far_m")
        hysteresis_m = _positive(
            tier.get("hysteresis_m", 0.0),
            f"{tier_id}.hysteresis_m",
            allow_zero=True,
        )
        if far_m <= near_m:
            raise ConfigError(f"{tier_id} must satisfy near_m < far_m")
        if index == 0 and near_m != 0.0:
            raise ConfigError("the first tier must start at 0 m")
        if index and not math.isclose(near_m, previous_far, abs_tol=1e-9):
            raise ConfigError(
                "tier distance bands must be ordered, contiguous, and non-overlapping"
            )
        tiers.append(TierConfig(tier_id, source, near_m, far_m, hysteresis_m))
        previous_far = far_m

    runtime_raw = _mapping(root.get("runtime", {}), "runtime")
    runtime = RuntimeConfig(
        update_interval_s=_positive(
            runtime_raw.get("update_interval_s", 0.05),
            "runtime.update_interval_s",
        ),
        translation_threshold_m=_positive(
            runtime_raw.get("translation_threshold_m", 0.05),
            "runtime.translation_threshold_m",
            allow_zero=True,
        ),
        rotation_threshold_deg=_positive(
            runtime_raw.get("rotation_threshold_deg", 0.25),
            "runtime.rotation_threshold_deg",
            allow_zero=True,
        ),
        fov_margin_deg=_positive(
            runtime_raw.get("fov_margin_deg", 2.0),
            "runtime.fov_margin_deg",
            allow_zero=True,
        ),
        multi_camera_mode=str(runtime_raw.get("multi_camera_mode", "active")),
        warmup_batch_size=int(runtime_raw.get("warmup_batch_size", 8)),
    )
    if runtime.multi_camera_mode not in {"active", "union"}:
        raise ConfigError("runtime.multi_camera_mode must be 'active' or 'union'")
    if runtime.warmup_batch_size < 1:
        raise ConfigError("runtime.warmup_batch_size must be at least 1")

    converter_raw = _mapping(root.get("converter", {}), "converter")
    command = converter_raw.get("command", list(ConverterConfig().command))
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise ConfigError("converter.command must be a list of strings")
    joined = "\0".join(command)
    if "{input}" not in joined or "{output}" not in joined:
        raise ConfigError("converter.command must include {input} and {output} placeholders")

    return BuildConfig(
        path=config_path,
        name=name,
        output_dir=output_dir,
        tile_size_m=tile_size_m,
        min_tile_points=min_tile_points,
        source_to_stage=matrix,
        tiers=tuple(tiers),
        runtime=runtime,
        converter=ConverterConfig(tuple(command)),
    )


def load_manifest(path: str | Path) -> Manifest:
    manifest_path = Path(path).resolve()
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid manifest JSON: {exc}") from exc
    manifest = Manifest.from_dict(_mapping(value, "manifest"))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Manifest) -> None:
    if manifest.schema != SCHEMA_VERSION:
        raise ConfigError(f"manifest schema must be {SCHEMA_VERSION!r}")
    if manifest.tile_size_m <= 0.0:
        raise ConfigError("manifest tile_size_m must be positive")
    tier_ids = [tier.id for tier in manifest.tiers]
    if len(tier_ids) != len(set(tier_ids)):
        raise ConfigError("manifest tier ids must be unique")
    known = set(tier_ids)
    tile_ids: set[str] = set()
    for tile in manifest.tiles:
        if tile.id in tile_ids:
            raise ConfigError(f"duplicate tile id: {tile.id}")
        tile_ids.add(tile.id)
        asset_tiers = [asset.tier_id for asset in tile.assets]
        if len(asset_tiers) != len(set(asset_tiers)):
            raise ConfigError(f"tile {tile.id} contains duplicate tier assets")
        unknown = set(asset_tiers) - known
        if unknown:
            raise ConfigError(f"tile {tile.id} references unknown tiers: {sorted(unknown)}")
        if np.any(np.asarray(tile.bounds.maximum) < np.asarray(tile.bounds.minimum)):
            raise ConfigError(f"tile {tile.id} has inverted bounds")
