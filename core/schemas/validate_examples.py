# -*- coding: utf-8 -*-
"""
Validate every example under core/schemas/examples/ against the Pricing Harness schemas.

Usage: python validate_examples.py

valid/*.json    must PASS   against client_input.schema.json
invalid/*.json  must FAIL   against client_input.schema.json (that's the point of them)
analysis_result_incomplete_example.json must PASS against analysis_result.schema.json
"""
import json
import sys
from pathlib import Path

import jsonschema

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.validation.validate_scenario_compare import (  # noqa: E402
    validate_scenario_compare_request,
    validate_scenario_compare_result,
)

CLIENT_INPUT_SCHEMA = json.loads((HERE / "client_input.schema.json").read_text(encoding="utf-8"))
ANALYSIS_RESULT_SCHEMA = json.loads((HERE / "analysis_result.schema.json").read_text(encoding="utf-8"))

results = []
all_ok = True


def check(label, instance_path, schema, expect_valid):
    global all_ok
    instance = json.loads(instance_path.read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft7Validator(schema).iter_errors(instance))
    passed = (len(errors) == 0) == expect_valid
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_ok = False
    detail = ""
    if errors:
        first = errors[0]
        detail = f"{first.message} (at {'/'.join(str(p) for p in first.absolute_path) or '<root>'})"
    results.append((status, label, "valid" if not errors else "invalid", detail))


for f in sorted((HERE / "examples" / "valid").glob("*.json")):
    check(f.name, f, CLIENT_INPUT_SCHEMA, expect_valid=True)

for f in sorted((HERE / "examples" / "invalid").glob("*.json")):
    check(f.name, f, CLIENT_INPUT_SCHEMA, expect_valid=False)

ar_example = HERE / "examples" / "analysis_result_incomplete_example.json"
check(ar_example.name, ar_example, ANALYSIS_RESULT_SCHEMA, expect_valid=True)


def check_scenario_compare(label, instance_path, validate_fn):
    global all_ok
    instance = json.loads(instance_path.read_text(encoding="utf-8"))
    errors = validate_fn(instance)
    passed = len(errors) == 0
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_ok = False
    detail = errors[0] if errors else ""
    results.append((status, label, "valid" if passed else "invalid", detail))


sc_dir = HERE / "examples" / "scenario_compare"
for f in sorted(sc_dir.glob("*.request.json")):
    check_scenario_compare(f.name, f, validate_scenario_compare_request)
for f in sorted(sc_dir.glob("*.result.json")):
    check_scenario_compare(f.name, f, validate_scenario_compare_result)

print(f"{'STATUS':6} {'FILE':45} {'SCHEMA RESULT':10} DETAIL")
for status, label, schema_result, detail in results:
    print(f"{status:6} {label:45} {schema_result:10} {detail}")

print()
if all_ok:
    print(f"ALL {len(results)} CHECKS PASSED")
    sys.exit(0)
else:
    print("SOME CHECKS FAILED")
    sys.exit(1)
