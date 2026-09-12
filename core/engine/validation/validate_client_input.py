# -*- coding: utf-8 -*-
"""Validate a Client Input document against core/schemas/client_input.schema.json."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "client_input.schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft7Validator(_SCHEMA)


def validate_client_input(instance: dict) -> list[str]:
    """Returns a list of human-readable error strings. Empty list = valid."""
    errors = sorted(_VALIDATOR.iter_errors(instance), key=lambda e: list(map(str, e.absolute_path)))
    return [
        f"{e.message} (at {'/'.join(str(p) for p in e.absolute_path) or '<root>'})"
        for e in errors
    ]


def assert_valid_client_input(instance: dict) -> None:
    errors = validate_client_input(instance)
    if errors:
        raise ValueError("Invalid Client Input:\n" + "\n".join(errors))
