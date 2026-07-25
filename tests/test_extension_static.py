from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "exts" / "mtg.isaac.gaussian_lod"


def test_extension_has_no_deprecated_isaac_namespace_or_user_paths() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in EXTENSION.rglob("*.py"))
    assert "omni.isaac." not in source
    assert "C:\\Users\\" not in source
    assert "/home/" not in source


def test_extension_declares_rt2_test_and_two_python_modules() -> None:
    config = (EXTENSION / "config" / "extension.toml").read_text(encoding="utf-8")
    assert "RayTracedLighting" in config
    assert 'name = "mtg_isaac_gaussian_lod"' in config
    assert 'name = "gaussian_lod_toolkit"' in config
