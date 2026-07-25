from __future__ import annotations

from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement

FIELDS = [
    ("x", "f4"),
    ("y", "f4"),
    ("z", "f4"),
    ("scale_0", "f4"),
    ("scale_1", "f4"),
    ("scale_2", "f4"),
    ("rot_0", "f4"),
    ("rot_1", "f4"),
    ("rot_2", "f4"),
    ("rot_3", "f4"),
    ("opacity", "f4"),
    ("f_dc_0", "f4"),
    ("f_dc_1", "f4"),
    ("f_dc_2", "f4"),
]


def write_splat(path: Path, positions: list[tuple[float, float, float]]) -> None:
    vertices = np.zeros(len(positions), dtype=FIELDS)
    for index, position in enumerate(positions):
        vertices["x"][index], vertices["y"][index], vertices["z"][index] = position
    vertices["scale_0"] = np.log(0.1)
    vertices["scale_1"] = np.log(0.1)
    vertices["scale_2"] = np.log(0.1)
    vertices["rot_0"] = 1.0
    vertices["opacity"] = 1.0
    PlyData(
        [PlyElement.describe(vertices, "vertex")],
        text=False,
        byte_order="<",
    ).write(str(path))
