# -*- coding: utf-8 -*-
"""
Validate scenario_compare request/result documents against core/schemas/
scenario_compare_request.schema.json and scenario_compare_result.schema.json.

Both schemas $ref across files (into analysis_result.schema.json's mode_a_block/mode_b_block/
mode_c_block/bep_block/metric/module_status/metric_status definitions, and scenario_compare_
request.schema.json $refs client_input.schema.json wholesale for base_input) — this needs a
multi-document registry, not a single-file jsonschema.Draft7Validator like client_input's own
validator uses. Built with the `referencing` library (not the deprecated jsonschema.RefResolver)
for correct cross-file $ref resolution.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

_CLIENT_INPUT = json.loads((_SCHEMAS_DIR / "client_input.schema.json").read_text(encoding="utf-8"))
_ANALYSIS_RESULT = json.loads((_SCHEMAS_DIR / "analysis_result.schema.json").read_text(encoding="utf-8"))
_REQUEST_SCHEMA = json.loads((_SCHEMAS_DIR / "scenario_compare_request.schema.json").read_text(encoding="utf-8"))
_RESULT_SCHEMA = json.loads((_SCHEMAS_DIR / "scenario_compare_result.schema.json").read_text(encoding="utf-8"))

_REGISTRY = Registry().with_resources([
    (_CLIENT_INPUT["$id"], Resource.from_contents(_CLIENT_INPUT)),
    (_ANALYSIS_RESULT["$id"], Resource.from_contents(_ANALYSIS_RESULT)),
    (_REQUEST_SCHEMA["$id"], Resource.from_contents(_REQUEST_SCHEMA)),
    (_RESULT_SCHEMA["$id"], Resource.from_contents(_RESULT_SCHEMA)),
])

_REQUEST_VALIDATOR = jsonschema.Draft7Validator(_REQUEST_SCHEMA, registry=_REGISTRY)
_RESULT_VALIDATOR = jsonschema.Draft7Validator(_RESULT_SCHEMA, registry=_REGISTRY)


def _errors(validator, instance):
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(map(str, e.absolute_path)))
    return [
        f"{e.message} (at {'/'.join(str(p) for p in e.absolute_path) or '<root>'})"
        for e in errors
    ]


def validate_scenario_compare_request(instance: dict) -> list[str]:
    return _errors(_REQUEST_VALIDATOR, instance)


def validate_scenario_compare_result(instance: dict) -> list[str]:
    return _errors(_RESULT_VALIDATOR, instance)


def assert_valid_scenario_compare_request(instance: dict) -> None:
    errors = validate_scenario_compare_request(instance)
    if errors:
        raise ValueError("Invalid Scenario Compare Request:\n" + "\n".join(errors))


def assert_valid_scenario_compare_result(instance: dict) -> None:
    errors = validate_scenario_compare_result(instance)
    if errors:
        raise ValueError("Invalid Scenario Compare Result:\n" + "\n".join(errors))
