from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "exts" / "mtg.isaac.gaussian_lod"
sys.path.insert(0, str(PACKAGE_ROOT))
