# -*- coding: utf-8 -*-
"""
Unit tests for Volume Profit (core/engine/modes/volume_profit.py).

Every rule asserted here is taken from docs/features/volume_profit/SPEC.md; section numbers are
cited per test. Numeric expectations come from the SPEC's §14 worked example (hand-calculated
there first, then confirmed here): N = 35,000 / 1.10, CMu = 14,443.18, FC = 2,000,000,
Q_BEP = 138.4736. Fixtures are intentionally independent from core/schemas/examples/.
"""
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.modes.volume_profit import run_volume_profit  # noqa: E402
from core.engine.result_builder import build_analysis_result  # noqa: E402
from core.engine.validation.validate_client_input import (  # noqa: E402
    assert_valid_client_input,
    validate_client_input,
)

ANALYSIS_RESULT_SCHEMA = json.loads(
    (ROOT / "core" / "schemas" / "analysis_result.schema.json").read_text(encoding="utf-8"))

Q_BEP = 2_000_000 / (35000 / 1.1 - 13500 - 3000 - 0.025 * 35000)


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def cost(item_id, category, amount=None, rate=None, basis="per_unit", applies="main", rule=None):
    item = {"item_id": item_id, "label": item_id, "cost_category": category, "amount": amount,
            "rate": rate, "currency": "KRW" if amount is not None else None, "basis": basis,
            "applies_to_component": applies}
    if rule:
        item["allocation_rule"] = rule
    return item


def default_items(*, shipping_basis="per_order", fc_basis="per_month", fc_applies="main", fc_rule=None):
    return [
        cost("material", "product_service_direct_cost", 12000),
        cost("packaging", "product_service_direct_cost", 1500),
        cost("pg_fee", "variable_selling_delivery", rate=0.025, basis="rate_of_gross_payment"),
        cost("shipping", "variable_selling_delivery", 3000, basis=shipping_basis),
        cost("fixed_ops", "fixed_operating_cost", 2_000_000, basis=fc_basis, applies=fc_applies, rule=fc_rule),
    ]


def make_input(*, items=None, plan=..., price=35000, includes_vat=True, extra_components=None):
    """`plan=...` (default) is the standard 200-unit monthly plan; pass None to omit sales_plan."""
    components = [{"component_id": "main", "type": "one_time", "actual_price": price,
                   "currency": "KRW", "price_includes_vat": includes_vat}]
    if extra_components:
        components.extend(extra_components)
    ci = {
        "schema_version": "1.2", "client_id": "unit_test_co", "case_id": "unit_test_case_vp",
        "product": {"name": "vp_test", "pricing_model": "one_time", "price_components": components},
        "tax": {"vat_rate": 0.10},
        "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
        "costs": {"items": items if items is not None else default_items()},
        "targets": {"target_contribution_margin_rate": None},
        "meta": {},
    }
    if plan is ...:
        plan = {"planned_quantity": 200, "period_basis": "per_month"}
    if plan is not None:
        ci["sales_plan"] = plan
    return ci


def run(ci, validate=True):
    if validate:
        assert_valid_client_input(ci)
    result = run_volume_profit(ci)
    return result, result["per_component"].get("main")


def codes(result):
    return [w["code"] for w in result["warnings"]]


def plan(q, period="per_month"):
    return {"planned_quantity": q, "period_basis": period}


# --- worked example (SPEC §14) --------------------------------------------------------------------
def test_worked_example_values_match_spec_section_14():
    result, c = run(make_input(items=default_items(shipping_basis="per_unit")))
    assert result["status"] == "OK"
    assert approx(c["total_net_sales_ex_vat"]["value"], 6_363_636.3636)
    assert approx(c["total_contribution_margin"]["value"], 2_888_636.3636)
    assert approx(c["operating_profit"]["value"], 888_636.3636)
    assert approx(c["operating_profit_rate"]["value"], 0.13964, 1e-4)
    assert approx(c["break_even_quantity_exact"]["value"], Q_BEP)
    assert approx(c["margin_of_safety_quantity"]["value"], 200 - Q_BEP)
    assert approx(c["margin_of_safety_rate"]["value"], (200 - Q_BEP) / 200)
    assert c["analysis_period_basis"] == "per_month"
    assert c["planned_quantity"] == {"value": 200, "status": "OK", "unit": "units"}
    assert {m["status"] for k, m in c.items() if k != "analysis_period_basis"} == {"OK"}
    assert result["warnings"] == []


def test_vat_exclusive_price_gives_same_economics():
    # price_includes_vat=False: N is the price itself; G = N x 1.1, so use 32,000 ex-VAT.
    ci = make_input(items=default_items(shipping_basis="per_unit"), price=32000, includes_vat=False)
    _, c = run(ci)
    n = 32000
    cmu = n - 13500 - 3000 - 0.025 * (n * 1.1)
    assert approx(c["operating_profit"]["value"], cmu * 200 - 2_000_000)


# --- per_order assumption (SPEC §11) --------------------------------------------------------------
def test_per_order_cost_makes_cost_dependent_metrics_estimated_with_warning():
    result, c = run(make_input())
    assert c["total_net_sales_ex_vat"]["status"] == "OK"  # does not depend on cost
    assert c["planned_quantity"]["status"] == "OK"
    for name in ("total_contribution_margin", "operating_profit", "operating_profit_rate",
                 "break_even_quantity_exact", "margin_of_safety_quantity", "margin_of_safety_rate"):
        assert c[name]["status"] == "ESTIMATED", name
    assert "ASSUMES_ONE_UNIT_PER_ORDER" in codes(result)
    assert result["status"] == "OK"  # ESTIMATED never lowers module status


def test_per_unit_cost_is_not_estimated():
    result, c = run(make_input(items=default_items(shipping_basis="per_unit")))
    assert "ASSUMES_ONE_UNIT_PER_ORDER" not in codes(result)
    assert c["operating_profit"]["status"] == "OK"


# --- gate order (SPEC §5) -------------------------------------------------------------------------
def test_no_sales_plan_is_not_run():
    result, c = run(make_input(plan=None))
    assert result == {"status": "NOT_RUN", "per_component": {}, "warnings": []}


def test_multi_component_is_error_with_empty_per_component():
    extra = [{"component_id": "saas", "type": "recurring_monthly", "actual_price": 10000,
              "currency": "KRW", "price_includes_vat": False}]
    result, c = run(make_input(extra_components=extra))
    assert result["status"] == "ERROR"
    assert result["per_component"] == {}
    assert codes(result) == ["MULTI_COMPONENT_VOLUME_PROFIT_NOT_SUPPORTED"]


def test_no_sales_plan_gate_runs_before_multi_component_gate():
    extra = [{"component_id": "saas", "type": "recurring_monthly", "actual_price": 10000,
              "currency": "KRW", "price_includes_vat": False}]
    result, _ = run(make_input(plan=None, extra_components=extra))
    assert result["status"] == "NOT_RUN"


# --- quantity semantics (SPEC §7, §9) -------------------------------------------------------------
def test_null_quantity_is_unknown_but_break_even_is_still_computed():
    result, c = run(make_input(plan=plan(None)))
    assert result["status"] == "INCOMPLETE"
    for name in ("planned_quantity", "total_net_sales_ex_vat", "total_contribution_margin",
                 "operating_profit", "operating_profit_rate", "margin_of_safety_quantity",
                 "margin_of_safety_rate"):
        assert c[name]["status"] == "UNKNOWN", name
        assert c[name]["value"] is None
    assert c["break_even_quantity_exact"]["status"] == "ESTIMATED"  # Q-independent, per_order item
    assert approx(c["break_even_quantity_exact"]["value"], Q_BEP)
    leaf = [w for w in result["warnings"] if w["code"] == "MISSING_DEPENDENCY"]
    assert leaf[0]["metric_path"].endswith("planned_quantity")
    assert leaf[0]["dependency_paths"] == ["sales_plan.planned_quantity"]


def test_missing_period_basis_is_unknown_not_assumed_monthly():
    result, c = run(make_input(plan={"planned_quantity": 200}))
    assert c["planned_quantity"]["status"] == "UNKNOWN"
    assert c["operating_profit"]["status"] == "UNKNOWN"
    leaf = [w for w in result["warnings"] if w["code"] == "MISSING_DEPENDENCY"][0]
    assert leaf["dependency_paths"] == ["sales_plan.period_basis"]


def test_negative_quantity_is_error_even_without_the_validator():
    result, c = run(make_input(plan=plan(-5)), validate=False)
    assert result["status"] == "ERROR"
    assert c["planned_quantity"]["status"] == "ERROR"
    assert "INVALID_NEGATIVE_QUANTITY" in codes(result)


def test_unsupported_period_is_error():
    result, c = run(make_input(plan=plan(200, period="per_year")), validate=False)
    assert c["planned_quantity"]["status"] == "ERROR"
    assert "UNSUPPORTED_PLAN_PERIOD" in codes(result)


def test_zero_quantity_is_a_valid_plan():
    result, c = run(make_input(items=default_items(shipping_basis="per_unit"), plan=plan(0)))
    assert result["status"] == "OK"
    assert c["total_net_sales_ex_vat"]["value"] == 0
    assert c["total_contribution_margin"]["value"] == 0
    assert approx(c["operating_profit"]["value"], -2_000_000)
    assert c["operating_profit_rate"]["status"] == "NOT_APPLICABLE"
    assert c["margin_of_safety_rate"]["status"] == "NOT_APPLICABLE"
    assert approx(c["margin_of_safety_quantity"]["value"], -Q_BEP)
    assert {"ZERO_NET_SALES_RATE_UNDEFINED", "ZERO_QUANTITY_RATE_UNDEFINED",
            "BELOW_BREAK_EVEN"} <= set(codes(result))


# --- margin of safety sign semantics (SPEC §8) ----------------------------------------------------
def test_plan_below_break_even_keeps_negative_value_with_ok_status_and_warning():
    result, c = run(make_input(items=default_items(shipping_basis="per_unit"), plan=plan(100)))
    assert approx(c["margin_of_safety_quantity"]["value"], 100 - Q_BEP)
    assert c["margin_of_safety_quantity"]["status"] == "OK"
    assert c["margin_of_safety_rate"]["value"] < 0
    assert c["operating_profit"]["value"] < 0
    assert "BELOW_BREAK_EVEN" in codes(result)
    assert result["status"] == "OK"


def test_plan_above_break_even_has_no_below_break_even_warning():
    result, _ = run(make_input(items=default_items(shipping_basis="per_unit"), plan=plan(300)))
    assert "BELOW_BREAK_EVEN" not in codes(result)


def test_plan_exactly_at_break_even_is_zero_margin_of_safety():
    items = [cost("d", "product_service_direct_cost", 400),
             cost("fc", "fixed_operating_cost", 50000, basis="per_month")]
    ci = make_input(items=items, price=1000, includes_vat=False, plan=plan(None))
    ci["tax"]["vat_rate"] = 0.1
    # CMu = 600, FC = 50,000 -> Q_BEP = 83.333...; plan exactly that quantity.
    ci["sales_plan"]["planned_quantity"] = 50000 / 600
    result, c = run(ci)
    assert approx(c["margin_of_safety_quantity"]["value"], 0, 1e-9)
    assert approx(c["operating_profit"]["value"], 0, 1e-9)


# --- CMu <= 0 (SPEC §8) ---------------------------------------------------------------------------
def test_negative_margin_per_unit_is_a_computed_loss_and_break_even_not_applicable():
    items = [cost("d", "product_service_direct_cost", 1200),
             cost("fc", "fixed_operating_cost", 50000, basis="per_month")]
    result, c = run(make_input(items=items, price=1000, includes_vat=False, plan=plan(10)))
    assert c["break_even_quantity_exact"]["status"] == "NOT_APPLICABLE"
    assert c["break_even_quantity_exact"]["value"] is None
    assert c["margin_of_safety_quantity"]["status"] == "NOT_APPLICABLE"
    assert c["margin_of_safety_rate"]["status"] == "NOT_APPLICABLE"
    assert approx(c["operating_profit"]["value"], -200 * 10 - 50000)  # still computed
    assert c["operating_profit"]["status"] == "OK"
    assert result["status"] == "OK"  # NOT_APPLICABLE does not lower module status
    assert "BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN" in codes(result)


def test_zero_margin_with_and_without_fixed_cost_uses_distinct_codes():
    d = cost("d", "product_service_direct_cost", 1000)
    with_fc = run(make_input(items=[d, cost("fc", "fixed_operating_cost", 5000, basis="per_month")],
                             price=1000, includes_vat=False, plan=plan(10)))[0]
    no_fc = run(make_input(items=[d, cost("fc", "fixed_operating_cost", 0, basis="per_month")],
                           price=1000, includes_vat=False, plan=plan(10)))[0]
    assert "BREAK_EVEN_UNDEFINED_ZERO_MARGIN" in codes(with_fc)
    assert "BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST" in codes(no_fc)


# --- fixed cost (SPEC §6) -------------------------------------------------------------------------
def test_no_fixed_cost_item_is_confirmed_zero_with_null_period_basis():
    items = [i for i in default_items(shipping_basis="per_unit") if i["cost_category"] != "fixed_operating_cost"]
    _, c = run(make_input(items=items))
    assert c["analysis_period_basis"] is None
    assert approx(c["operating_profit"]["value"], c["total_contribution_margin"]["value"])
    assert c["break_even_quantity_exact"]["value"] == 0


def test_fixed_cost_basis_other_than_per_month_is_error():
    result, c = run(make_input(items=default_items(fc_basis="per_unit_per_month")))
    assert result["status"] == "ERROR"
    assert c["operating_profit"]["status"] == "ERROR"
    assert "UNSUPPORTED_FIXED_COST_BASIS_FOR_VOLUME" in codes(result)


def test_inconsistent_fixed_cost_basis_reuses_bep_code():
    items = default_items() + [cost("fc2", "fixed_operating_cost", 1000, basis="per_visit")]
    result, _ = run(make_input(items=items))
    assert "INCONSISTENT_FIXED_COST_BASIS" in codes(result)


def test_shared_blended_only_fixed_cost_is_unknown_not_excluded():
    result, c = run(make_input(items=default_items(fc_applies="shared", fc_rule="blended_only")))
    assert result["status"] == "INCOMPLETE"
    assert c["operating_profit"]["status"] == "UNKNOWN"
    assert "FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED" in codes(result)
    assert c["total_contribution_margin"]["status"] == "ESTIMATED"  # unaffected by FC


def test_negative_fixed_cost_amount_is_error():
    items = default_items()
    items[-1]["amount"] = -1
    result, _ = run(make_input(items=items), validate=False)
    assert "INVALID_NEGATIVE_COST" in codes(result)


# --- warning structure ----------------------------------------------------------------------------
def test_root_cause_warns_once_and_dependents_point_at_owner_metric():
    ci = make_input(items=default_items(shipping_basis="per_unit"))
    ci["product"]["price_components"][0]["actual_price"] = None
    result, c = run(ci)
    assert c["total_net_sales_ex_vat"]["status"] == "UNKNOWN"
    assert c["total_contribution_margin"]["status"] == "UNKNOWN"
    leaf = [w for w in result["warnings"] if w["code"] == "MISSING_DEPENDENCY"]
    assert len(leaf) == 1 and leaf[0]["metric_path"].endswith("total_net_sales_ex_vat")
    downstream = [w for w in result["warnings"] if w["metric_path"].endswith("total_contribution_margin")]
    assert downstream[0]["code"] == "DOWNSTREAM_UNKNOWN"
    assert downstream[0]["dependency_paths"] == [leaf[0]["metric_path"]]


# --- schema and result integration (SPEC §3) ------------------------------------------------------
def test_client_input_schema_accepts_sales_plan_and_rejects_bad_values():
    assert validate_client_input(make_input()) == []
    assert validate_client_input(make_input(plan=plan(None))) == []
    assert validate_client_input(make_input(plan=plan(-1)))  # negative quantity
    assert validate_client_input(make_input(plan=plan(10, period="per_year")))  # unsupported period
    assert validate_client_input(make_input(plan={"planned_quantity": 1, "extra": 1}))  # unknown key


def test_existing_client_inputs_without_sales_plan_stay_valid():
    assert validate_client_input(make_input(plan=None)) == []


def test_build_analysis_result_includes_volume_profit_and_validates():
    validator = jsonschema.Draft7Validator(ANALYSIS_RESULT_SCHEMA)
    for ci in (make_input(), make_input(plan=None), make_input(plan=plan(None)),
               make_input(items=default_items(fc_basis="per_visit"))):
        result = build_analysis_result(ci, client_input_ref="unit_test")
        assert list(validator.iter_errors(result)) == []
        assert result["schema_version"] == "1.2"
        assert "volume_profit" in result


def test_analysis_result_without_volume_profit_key_is_still_valid():
    result = build_analysis_result(make_input(plan=None), client_input_ref="unit_test")
    del result["volume_profit"]
    assert list(jsonschema.Draft7Validator(ANALYSIS_RESULT_SCHEMA).iter_errors(result)) == []


def test_missing_input_paths_include_sales_plan_but_not_own_result_paths():
    result = build_analysis_result(make_input(plan=plan(None)), client_input_ref="unit_test")
    paths = result["meta"]["missing_input_paths"]
    assert "sales_plan.planned_quantity" in paths
    assert not any(p.startswith("volume_profit.") for p in paths)
