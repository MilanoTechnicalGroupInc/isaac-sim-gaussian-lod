"""Safe subprocess adapter for NVIDIA's Gaussian Splat converter."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .models import ConverterConfig


class ConversionError(RuntimeError):
    """A tile could not be converted to native Gaussian USD."""


def convert_tile(
    input_ply: Path,
    output_usdz: Path,
    config: ConverterConfig,
    *,
    timeout_s: float = 900.0,
) -> None:
    output_usdz.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        part.replace("{input}", str(input_ply)).replace("{output}", str(output_usdz))
        for part in config.command
    ]
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
    if not output_usdz.is_file() or output_usdz.stat().st_size == 0:
        raise ConversionError(f"converter produced no asset: {output_usdz}")
