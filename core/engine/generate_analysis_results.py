# -*- coding: utf-8 -*-
"""
Runs MODE A over every core/schemas/examples/valid/*.json Client Input and writes the
resulting Analysis Result next to it under core/schemas/examples/analysis_results/,
validating each output against analysis_result.schema.json.

This both demonstrates the full vertical slice (Client Input -> Engine -> Analysis Result)
and doubles as a regression check: run again after any engine change and diff the output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import jsonschema  # noqa: E402

from core.engine.result_builder import build_analysis_result  # noqa: E402
from core.engine.validation.validate_client_input import validate_client_input  # noqa: E402

EXAMPLES_DIR = ROOT / "core" / "schemas" / "examples" / "valid"
OUT_DIR = ROOT / "core" / "schemas" / "examples" / "analysis_results"
ANALYSIS_RESULT_SCHEMA = json.loads(
    (ROOT / "core" / "schemas" / "analysis_result.schema.json").read_text(encoding="utf-8")
)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    validator = jsonschema.Draft7Validator(ANALYSIS_RESULT_SCHEMA)
    rows = []

    for f in sorted(EXAMPLES_DIR.glob("*.json")):
        client_input = json.loads(f.read_text(encoding="utf-8"))

        ci_errors = validate_client_input(client_input)
        if ci_errors:
            rows.append((f.name, "CLIENT_INPUT_INVALID", "; ".join(ci_errors)))
            continue

        result = build_analysis_result(client_input, client_input_ref=str(f.relative_to(ROOT)))
        ar_errors = list(validator.iter_errors(result))

        out_path = OUT_DIR / f"{f.stem}.analysis_result.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        status = "PASS" if not ar_errors else "FAIL"
        detail = "" if not ar_errors else ar_errors[0].message
        rows.append((f.name, f"SCHEMA_{status}", detail))
        rows.append((f.name, f"mode_a.status={result['mode_a']['status']}",
                     f"warnings={len(result['mode_a']['warnings'])}"))

    print(f"{'FILE':45} {'CHECK':30} DETAIL")
    for name, check, detail in rows:
        print(f"{name:45} {check:30} {detail}")


if __name__ == "__main__":
    main()
