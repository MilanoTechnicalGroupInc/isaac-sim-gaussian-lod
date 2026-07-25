"""Versioned configuration and manifest models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_VERSION = "mtg.isaac.gaussian_lod.v1"


@dataclass(frozen=True)
class Aabb:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    @property
    def center(self) -> np.ndarray:
        return (np.asarray(self.minimum, dtype=np.float64) + self.maximum) * 0.5

    @property
    def extent(self) -> np.ndarray:
        return (np.asarray(self.maximum, dtype=np.float64) - self.minimum) * 0.5

    def to_dict(self) -> dict[str, list[float]]:
        return {"min": list(self.minimum), "max": list(self.maximum)}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Aabb:
        return cls(tuple(map(float, value["min"])), tuple(map(float, value["max"])))


@dataclass(frozen=True)
class TierConfig:
    id: str
    source: Path
    near_m: float
    far_m: float
    hysteresis_m: float


@dataclass(frozen=True)
class RuntimeConfig:
    update_interval_s: float = 0.05
    translation_threshold_m: float = 0.05
    rotation_threshold_deg: float = 0.25
    fov_margin_deg: float = 2.0
    multi_camera_mode: str = "active"
    warmup_batch_size: int = 8


@dataclass(frozen=True)
class ConverterConfig:
    command: tuple[str, ...] = (
        "python",
        "-m",
        "usd_convert_gsplat",
        "-i",
        "{input}",
        "-o",
        "{output}",
        "--up-axis",
        "Z",
    )


@dataclass(frozen=True)
class BuildConfig:
    path: Path
    name: str
    output_dir: Path
    tile_size_m: float
    min_tile_points: int
    source_to_stage: np.ndarray
    tiers: tuple[TierConfig, ...]
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    converter: ConverterConfig = field(default_factory=ConverterConfig)


@dataclass(frozen=True)
class TileAsset:
    tier_id: str
    path: str
    point_count: int
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TileAsset:
        return cls(
            tier_id=str(value["tier_id"]),
            path=str(value["path"]),
            point_count=int(value["point_count"]),
            sha256=str(value["sha256"]),
            bytes=int(value["bytes"]),
        )


@dataclass(frozen=True)
class TileRecord:
    id: str
    key: tuple[int, int]
    bounds: Aabb
    assets: tuple[TileAsset, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": list(self.key),
            "bounds": self.bounds.to_dict(),
            "assets": [asset.to_dict() for asset in self.assets],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TileRecord:
        return cls(
            id=str(value["id"]),
            key=(int(value["key"][0]), int(value["key"][1])),
            bounds=Aabb.from_dict(value["bounds"]),
            assets=tuple(TileAsset.from_dict(item) for item in value["assets"]),
        )


@dataclass(frozen=True)
class ManifestTier:
    id: str
    near_m: float
    far_m: float
    hysteresis_m: float
    source_name: str
    source_sha256: str
    source_point_count: int
    included_point_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ManifestTier:
        return cls(
            id=str(value["id"]),
            near_m=float(value["near_m"]),
            far_m=float(value["far_m"]),
            hysteresis_m=float(value["hysteresis_m"]),
            source_name=str(value["source_name"]),
            source_sha256=str(value["source_sha256"]),
            source_point_count=int(value["source_point_count"]),
            included_point_count=int(value["included_point_count"]),
        )


@dataclass(frozen=True)
class Manifest:
    name: str
    tile_size_m: float
    grid_origin_xy: tuple[float, float]
    source_to_stage: tuple[tuple[float, float, float, float], ...]
    tiers: tuple[ManifestTier, ...]
    tiles: tuple[TileRecord, ...]
    runtime: RuntimeConfig
    schema: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "name": self.name,
            "tile_size_m": self.tile_size_m,
            "grid_origin_xy": list(self.grid_origin_xy),
            "source_to_stage": [list(row) for row in self.source_to_stage],
            "tiers": [tier.to_dict() for tier in self.tiers],
            "tiles": [tile.to_dict() for tile in self.tiles],
            "runtime": asdict(self.runtime),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Manifest:
        return cls(
            schema=str(value["schema"]),
            name=str(value["name"]),
            tile_size_m=float(value["tile_size_m"]),
            grid_origin_xy=(
                float(value["grid_origin_xy"][0]),
                float(value["grid_origin_xy"][1]),
            ),
            source_to_stage=tuple(
                tuple(float(component) for component in row) for row in value["source_to_stage"]
            ),
            tiers=tuple(ManifestTier.from_dict(item) for item in value["tiers"]),
            tiles=tuple(TileRecord.from_dict(item) for item in value["tiles"]),
            runtime=RuntimeConfig(**value.get("runtime", {})),
        )


@dataclass(frozen=True)
class CameraState:
    path: str
    position: tuple[float, float, float]
    right: tuple[float, float, float]
    up: tuple[float, float, float]
    forward: tuple[float, float, float]
    horizontal_fov_rad: float
    vertical_fov_rad: float
    near_m: float
    far_m: float
