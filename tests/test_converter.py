from __future__ import annotations

import sys
import types
from pathlib import Path

from gaussian_lod_toolkit.converter import convert_tile
from gaussian_lod_toolkit.models import ConverterConfig


def test_matching_interpreter_uses_in_process_converter(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "tile.ply"
    output = tmp_path / "tile.usdz"
    source.write_bytes(b"ply")
    calls: dict[str, object] = {}

    def read_ply(path: str) -> object:
        calls["input"] = path
        return object()

    def write_gaussian_splat_usd(
        _data,
        path: str,
        **options,
    ) -> str:
        calls["options"] = options
        Path(path).write_bytes(b"usdz")
        return path

    fake_module = types.ModuleType("usd_convert_gsplat")
    fake_module.read_ply = read_ply
    fake_module.write_gaussian_splat_usd = write_gaussian_splat_usd
    monkeypatch.setitem(sys.modules, "usd_convert_gsplat", fake_module)
    config = ConverterConfig(
        (
            sys.executable,
            "-m",
            "usd_convert_gsplat",
            "-i",
            "{input}",
            "-o",
            "{output}",
            "--up-axis",
            "Z",
        )
    )

    convert_tile(source, output, config)

    assert output.read_bytes() == b"usdz"
    assert calls["input"] == str(source)
    assert calls["options"]["up_axis"] == "Z"
