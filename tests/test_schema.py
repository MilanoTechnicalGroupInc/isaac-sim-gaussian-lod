from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_manifest_schema_is_valid_draft_2020_12() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
