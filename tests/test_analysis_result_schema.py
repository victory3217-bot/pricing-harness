# -*- coding: utf-8 -*-
"""
Schema-level tests for analysis_result.schema.json's MODE B block.

MODE B is now implemented and always produces a full per_component/warnings result (see
core/engine/modes/mode_b.py and docs/features/mode_b_target_price/SPEC.md section 9) — the
top-level `mode_b` property was tightened from the generic `module_block` ref to the strict
`mode_b_block` ref for exactly this reason. These tests pin that tightening: a `mode_b` block
missing `per_component`/`warnings`, or a per-component entry missing a required metric, must now
fail validation; a real (generated) INCOMPLETE result must still pass.
"""
import copy
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.result_builder import build_analysis_result  # noqa: E402
from core.engine.validation.validate_client_input import assert_valid_client_input  # noqa: E402

SCHEMA = json.loads((ROOT / "core" / "schemas" / "analysis_result.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft7Validator(SCHEMA)


def _minimal_valid_document(mode_b_block):
    """A full Analysis Result with every sibling block minimally valid, so a test can vary
    only `mode_b` and know any resulting failure is attributable to that block."""
    return {
        "schema_version": "1.1",
        "source": {
            "client_id": "unit_test_co",
            "case_id": "unit_test_case",
            "client_input_ref": "test",
            "engine_version": "0.2.0",
            "calculated_at": "2026-09-11T00:00:00+09:00",
        },
        "currency": {"reporting": "KRW"},
        "mode_a": {"status": "OK", "per_component": {}, "warnings": []},
        "blended": {"status": "NOT_IMPLEMENTED"},
        "mode_b": mode_b_block,
        "mode_c": {"status": "OK", "per_component": {}, "warnings": []},
        "bep": {"status": "OK", "per_component": {}, "warnings": []},
        "meta": {"missing_input_paths": []},
    }


def is_valid(document):
    return not list(VALIDATOR.iter_errors(document))


# ---------------------------------------------------------------------------
# mode_b.status = OK but per_component missing -> schema FAIL
# ---------------------------------------------------------------------------
def test_mode_b_ok_without_per_component_fails_schema():
    doc = _minimal_valid_document({"status": "OK"})
    assert not is_valid(doc)


# ---------------------------------------------------------------------------
# mode_b component missing a required metric -> schema FAIL
# ---------------------------------------------------------------------------
def test_mode_b_component_missing_required_metric_fails_schema():
    full_metric = {"value": 1.0, "status": "OK", "unit": "KRW"}
    incomplete_component = {
        "denominator": full_metric,
        "required_net_sales_ex_vat": full_metric,
        "required_gross_payment_incl_vat": full_metric,
        "required_selling_price": full_metric,
        "required_list_price": full_metric,
        "expected_contribution_margin": full_metric,
        # expected_contribution_margin_rate deliberately omitted
    }
    doc = _minimal_valid_document({
        "status": "OK",
        "per_component": {"main": incomplete_component},
        "warnings": [],
    })
    assert not is_valid(doc)


# ---------------------------------------------------------------------------
# a normal INCOMPLETE + UNKNOWN-metrics result -> schema PASS
# ---------------------------------------------------------------------------
def test_mode_b_incomplete_with_unknown_metrics_passes_schema():
    unknown_metric = {"value": None, "status": "UNKNOWN", "unit": "KRW"}
    unknown_ratio = {"value": None, "status": "UNKNOWN", "unit": "ratio"}
    component = {
        "denominator": unknown_ratio,
        "required_net_sales_ex_vat": unknown_metric,
        "required_gross_payment_incl_vat": unknown_metric,
        "required_selling_price": unknown_metric,
        "required_list_price": unknown_metric,
        "expected_contribution_margin": unknown_metric,
        "expected_contribution_margin_rate": unknown_ratio,
    }
    doc = _minimal_valid_document({
        "status": "INCOMPLETE",
        "per_component": {"main": component},
        "warnings": [{
            "code": "MISSING_DEPENDENCY",
            "severity": "blocking",
            "metric_path": "mode_b.per_component.main.denominator",
            "dependency_paths": ["targets.target_contribution_margin_rate"],
            "message": "목표 CM율이 미입력되어 분모를 계산할 수 없습니다.",
        }],
    })
    assert is_valid(doc)


# ---------------------------------------------------------------------------
# a real engine-generated result (target rate null -> everything UNKNOWN) must also validate --
# this is the actual case the schema tightening was meant to cover (no more NOT_IMPLEMENTED
# stub for a Client Input with no target rate).
# ---------------------------------------------------------------------------
def test_real_engine_output_with_no_target_rate_passes_strict_mode_b_schema():
    ci = json.loads((ROOT / "core/schemas/examples/valid/01_simple_one_time_product.json").read_text(encoding="utf-8"))
    ci = copy.deepcopy(ci)
    assert_valid_client_input(ci)
    result = build_analysis_result(ci, client_input_ref="test")
    assert result["mode_b"]["status"] == "INCOMPLETE"
    errors = list(VALIDATOR.iter_errors(result))
    assert not errors, [e.message for e in errors]


def _minimal_valid_document_mode_c(mode_c_block):
    """Same pattern as _minimal_valid_document, but varying mode_c instead of mode_b."""
    doc = _minimal_valid_document({"status": "OK", "per_component": {}, "warnings": []})
    doc["mode_c"] = mode_c_block
    return doc


# ---------------------------------------------------------------------------
# mode_c.status = OK but per_component missing -> schema FAIL
# ---------------------------------------------------------------------------
def test_mode_c_ok_without_per_component_fails_schema():
    doc = _minimal_valid_document_mode_c({"status": "OK"})
    assert not is_valid(doc)


# ---------------------------------------------------------------------------
# mode_c component missing a required metric -> schema FAIL
# ---------------------------------------------------------------------------
def test_mode_c_component_missing_required_metric_fails_schema():
    full_metric = {"value": 1.0, "status": "OK", "unit": "KRW"}
    incomplete_component = {
        "market_net_sales_ex_vat": full_metric,
        "market_gross_payment_incl_vat": full_metric,
        "allowable_direct_cost": full_metric,
        "actual_direct_cost": full_metric,
        "direct_cost_gap": full_metric,
        "expected_contribution_margin": full_metric,
        # expected_contribution_margin_rate deliberately omitted
    }
    doc = _minimal_valid_document_mode_c({
        "status": "OK",
        "per_component": {"main": incomplete_component},
        "warnings": [],
    })
    assert not is_valid(doc)


# ---------------------------------------------------------------------------
# a normal INCOMPLETE + UNKNOWN-metrics MODE C result -> schema PASS
# ---------------------------------------------------------------------------
def test_mode_c_incomplete_with_unknown_metrics_passes_schema():
    unknown_metric = {"value": None, "status": "UNKNOWN", "unit": "KRW"}
    unknown_ratio = {"value": None, "status": "UNKNOWN", "unit": "ratio"}
    component = {
        "market_net_sales_ex_vat": unknown_metric,
        "market_gross_payment_incl_vat": unknown_metric,
        "allowable_direct_cost": unknown_metric,
        "actual_direct_cost": unknown_metric,
        "direct_cost_gap": unknown_metric,
        "expected_contribution_margin": unknown_metric,
        "expected_contribution_margin_rate": unknown_ratio,
    }
    doc = _minimal_valid_document_mode_c({
        "status": "INCOMPLETE",
        "per_component": {"main": component},
        "warnings": [{
            "code": "MISSING_DEPENDENCY",
            "severity": "blocking",
            "metric_path": "mode_c.per_component.main.market_net_sales_ex_vat",
            "dependency_paths": ["product.price_components[main].target_market_price"],
            "message": "시장가격이 미입력되어 계산할 수 없습니다.",
        }],
    })
    assert is_valid(doc)


# ---------------------------------------------------------------------------
# a real engine-generated MODE C result (no target price/rate -> everything UNKNOWN) must also
# validate against the strict mode_c schema.
# ---------------------------------------------------------------------------
def test_real_engine_output_with_no_target_price_passes_strict_mode_c_schema():
    ci = json.loads((ROOT / "core/schemas/examples/valid/01_simple_one_time_product.json").read_text(encoding="utf-8"))
    ci = copy.deepcopy(ci)
    assert_valid_client_input(ci)
    result = build_analysis_result(ci, client_input_ref="test")
    assert result["mode_c"]["status"] == "INCOMPLETE"
    errors = list(VALIDATOR.iter_errors(result))
    assert not errors, [e.message for e in errors]
