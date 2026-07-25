"""Adapter for NVIDIA's Gaussian Splat converter."""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
from pathlib import Path

from .models import ConverterConfig


class ConversionError(RuntimeError):
    """A tile could not be converted to native Gaussian USD."""


def _option(arguments: list[str], name: str, default: str) -> str:
    try:
        return arguments[arguments.index(name) + 1]
    except (ValueError, IndexError):
        return default


def _can_convert_in_process(arguments: list[str]) -> bool:
    if len(arguments) < 3 or arguments[1:3] != ["-m", "usd_convert_gsplat"]:
        return False
    try:
        return Path(arguments[0]).resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def _convert_in_process(
    input_ply: Path,
    output_asset: Path,
    arguments: list[str],
) -> None:
    try:
        from usd_convert_gsplat import read_ply, write_gaussian_splat_usd
    except ImportError as exc:
        raise ConversionError(
            "in-process conversion requires usd-convert-gsplat in the active environment"
        ) from exc

    rotation = tuple(
        float(_option(arguments, option, "0"))
        for option in ("--rotate-x", "--rotate-y", "--rotate-z")
    )
    prim_name = _option(arguments, "--name", "") or None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            splat_data = read_ply(str(input_ply))
            actual_path = write_gaussian_splat_usd(
                splat_data,
                str(output_asset),
                source_file=str(input_ply),
                prim_name=prim_name,
                up_axis=_option(arguments, "--up-axis", "Y").upper(),
                rotation_degrees=rotation,
            )
    except Exception as exc:
        raise ConversionError(f"converter failed for {input_ply.name}: {exc}") from exc
    if Path(actual_path).resolve() != output_asset.resolve():
        raise ConversionError(f"converter wrote an unexpected output path: {actual_path}")


def convert_tile(
    input_ply: Path,
    output_asset: Path,
    config: ConverterConfig,
    *,
    timeout_s: float = 900.0,
) -> None:
    output_asset.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        part.replace("{input}", str(input_ply)).replace("{output}", str(output_asset))
        for part in config.command
    ]
    if _can_convert_in_process(arguments):
        _convert_in_process(input_ply, output_asset, arguments)
        if not output_asset.is_file() or output_asset.stat().st_size == 0:
            raise ConversionError(f"converter produced no asset: {output_asset}")
        return
    try:
        result = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise ConversionError(
            f"converter executable was not found: {arguments[0]!r}; run from the "
            "Isaac Sim Python environment or configure converter.command"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"converter timed out for {input_ply.name}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ConversionError(
            f"converter failed for {input_ply.name} with exit code "
            f"{result.returncode}: {detail[-2000:]}"
        )
    if not output_asset.is_file() or output_asset.stat().st_size == 0:
        raise ConversionError(f"converter produced no asset: {output_asset}")
