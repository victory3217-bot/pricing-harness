# -*- coding: utf-8 -*-
"""
Unit tests for MODE C (core/engine/modes/mode_c.py).

Every numeric expectation here is hand-checked against
docs/features/mode_c_allowable_cost/CASE.md (TC1-TC20) — this file's test numbers are labeled
with which CASE.md TC they match. Fixtures are intentionally minimal and independent from
core/schemas/examples/ (which exist to demonstrate the schema, not pin exact engine outputs).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.modes.mode_c import run_mode_c  # noqa: E402
from core.engine.result_builder import build_analysis_result  # noqa: E402
from core.engine.validation.validate_client_input import assert_valid_client_input  # noqa: E402

APPROX = 1e-4


def approx(a, b, tol=APPROX):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def make_input(*, price, price_includes_vat, vat_rate, target_cm_rate,
                fixed_variable_cost=None, net_sales_fee_rate=None, gross_payment_fee_rate=None,
                actual_direct_cost=None, extra_cost_items=None, price_is_null=False,
                component_id="main", currency="KRW"):
    """Builds a minimal single-component Client Input for MODE C.

    fixed_variable_cost -> F (variable_selling_delivery, amount-based).
    net_sales_fee_rate -> b (rate_of_net_sales), omitted if None.
    gross_payment_fee_rate -> a (rate_of_gross_payment), omitted if None.
    actual_direct_cost -> a product_service_direct_cost item (separate from F/b/a), omitted if None.
    """
    items = []
    if fixed_variable_cost is not None:
        items.append({
            "item_id": "F", "label": "고정 변동비", "cost_category": "variable_selling_delivery",
            "amount": fixed_variable_cost, "rate": None, "currency": currency, "basis": "per_order",
            "applies_to_component": component_id,
        })
    if net_sales_fee_rate is not None:
        items.append({
            "item_id": "b", "label": "net-sales fee", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": net_sales_fee_rate, "currency": None, "basis": "rate_of_net_sales",
            "applies_to_component": component_id,
        })
    if gross_payment_fee_rate is not None:
        items.append({
            "item_id": "a", "label": "gross-payment fee", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": gross_payment_fee_rate, "currency": None, "basis": "rate_of_gross_payment",
            "applies_to_component": component_id,
        })
    if actual_direct_cost is not None:
        items.append({
            "item_id": "direct", "label": "실제 직접원가", "cost_category": "product_service_direct_cost",
            "amount": actual_direct_cost, "rate": None, "currency": currency, "basis": "per_unit",
            "applies_to_component": component_id,
        })
    if extra_cost_items:
        items.extend(extra_cost_items)

    component = {
        "component_id": component_id,
        "type": "one_time",
        "actual_price": None,  # required by schema, unused by MODE C (see SPEC.md section 1a)
        "currency": currency,
        "price_includes_vat": price_includes_vat,
        "target_market_price": None if price_is_null else price,
    }

    return {
        "schema_version": "1.1",
        "client_id": "unit_test_co",
        "case_id": "unit_test_case_mode_c",
        "product": {
            "name": "MODE C 테스트 상품",
            "pricing_model": "one_time",
            "price_components": [component],
        },
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": currency, "reporting_currency": currency, "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": target_cm_rate},
        "meta": {"entered_by": "unit_test", "entered_at": "2026-09-11", "notes": ""},
    }


def m(result, name, component_id="main"):
    return result["per_component"][component_id][name]


# ---------------------------------------------------------------------------
# 1. simple, no fee at all (TC1)
# ---------------------------------------------------------------------------
def test_1_simple_no_fee():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3)
    assert_valid_client_input(ci)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 70000)


# ---------------------------------------------------------------------------
# 2. fixed-amount non-product variable cost (TC2)
# ---------------------------------------------------------------------------
def test_2_fixed_variable_cost():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     fixed_variable_cost=5000)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 65000)


# ---------------------------------------------------------------------------
# 3. net-sales fee only (TC3)
# ---------------------------------------------------------------------------
def test_3_net_sales_fee_only():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     net_sales_fee_rate=0.1)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 60000)


# ---------------------------------------------------------------------------
# 4. gross-payment fee, v known, VAT-exclusive display (TC4)
# ---------------------------------------------------------------------------
def test_4_gross_payment_fee_vat_exclusive():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     gross_payment_fee_rate=0.05)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 64500)


# ---------------------------------------------------------------------------
# 5. VAT-inclusive display, both fee types (TC5)
# ---------------------------------------------------------------------------
def test_5_vat_inclusive_display_both_fees():
    ci = make_input(price=110000, price_includes_vat=True, vat_rate=0.10, target_cm_rate=0.3,
                     fixed_variable_cost=1000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 55700, tol=1e-3)


# ---------------------------------------------------------------------------
# 6. VAT-exclusive display, same underlying economics as TC5 (TC6)
# ---------------------------------------------------------------------------
def test_6_vat_exclusive_display_same_economics_as_5():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     fixed_variable_cost=1000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 55700, tol=1e-3)


# ---------------------------------------------------------------------------
# 7. VAT-exclusive, v UNKNOWN, a=0 (TC7)
# ---------------------------------------------------------------------------
def test_7_vat_exclusive_v_unknown_a_zero():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=None, target_cm_rate=0.3,
                     fixed_variable_cost=1000, net_sales_fee_rate=0.1)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 59000)
    g = m(result, "market_gross_payment_incl_vat")
    assert g["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 8. VAT-exclusive, v UNKNOWN, a>0 (TC8)
# ---------------------------------------------------------------------------
def test_8_vat_exclusive_v_unknown_a_positive():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=None, target_cm_rate=0.3,
                     gross_payment_fee_rate=0.05)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "UNKNOWN"
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_c.per_component.main.allowable_direct_cost")
    assert "tax.vat_rate" in warning["dependency_paths"] or "mode_c.per_component.main.market_gross_payment_incl_vat" in warning["dependency_paths"]


# ---------------------------------------------------------------------------
# 9. target CM rate UNKNOWN (TC9)
# ---------------------------------------------------------------------------
def test_9_target_cm_null():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=None)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "UNKNOWN"
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_c.per_component.main.allowable_direct_cost")
    assert "targets.target_contribution_margin_rate" in warning["dependency_paths"]


# ---------------------------------------------------------------------------
# 10. target CM rate invalid, t >= 1 (TC10)
# ---------------------------------------------------------------------------
def test_10_target_cm_invalid_ge_one():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=1.0)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "ERROR"
    assert adc["value"] is None
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 11. negative allowable direct cost — valid, not clamped, not ERROR (TC11)
# ---------------------------------------------------------------------------
def test_11_negative_adc_is_ok_with_warning():
    ci = make_input(price=10000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.5,
                     net_sales_fee_rate=0.3, gross_payment_fee_rate=0.3)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], -1300, tol=1e-3)
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_c.per_component.main.allowable_direct_cost")
    assert warning["code"] == "NEGATIVE_ALLOWABLE_COST"
    assert warning["severity"] == "warning"
    # module status must stay OK -- a non-blocking warning must not make the module INCOMPLETE/ERROR
    assert result["status"] == "OK"
    # self-check: expected CMR should still equal t exactly
    cmr = m(result, "expected_contribution_margin_rate")
    assert cmr["status"] == "OK"
    assert approx(cmr["value"], 0.5)


# ---------------------------------------------------------------------------
# 12. actual direct cost below allowable (gap > 0) (TC12)
# ---------------------------------------------------------------------------
def test_12_actual_below_allowable_gap_positive():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     actual_direct_cost=50000)
    result = run_mode_c(ci)
    gap = m(result, "direct_cost_gap")
    assert gap["status"] == "OK"
    assert approx(gap["value"], 20000)


# ---------------------------------------------------------------------------
# 13. actual direct cost above allowable (gap < 0) (TC13)
# ---------------------------------------------------------------------------
def test_13_actual_above_allowable_gap_negative():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     actual_direct_cost=90000)
    result = run_mode_c(ci)
    gap = m(result, "direct_cost_gap")
    assert gap["status"] == "OK"
    assert approx(gap["value"], -20000)


# ---------------------------------------------------------------------------
# 14. unresolved shared variable cost -> F/b/a UNKNOWN -> ADC UNKNOWN (TC14)
# ---------------------------------------------------------------------------
def test_14_shared_variable_cost_unresolved_blocks_adc():
    ci = make_input(
        price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "shared_f", "label": "공유 변동비", "cost_category": "variable_selling_delivery",
            "amount": 1000, "rate": None, "currency": "KRW", "basis": "per_order",
            "applies_to_component": "shared", "allocation_rule": "by_component_revenue",
        }],
    )
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "UNKNOWN"
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_c.per_component.main.allowable_direct_cost")
    assert warning["code"] == "UNSUPPORTED_SHARED_COST_ALLOCATION"
    assert "blended.allocation[shared_f]" in warning["dependency_paths"]


# ---------------------------------------------------------------------------
# 15. shared + direct invalid configuration -> ERROR (TC15)
# ---------------------------------------------------------------------------
def test_15_shared_plus_direct_invalid_configuration():
    ci = make_input(
        price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "shared_b", "label": "모순 설정", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
            "applies_to_component": "shared", "allocation_rule": "direct",
        }],
    )
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "ERROR"
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_c.per_component.main.allowable_direct_cost")
    assert warning["code"] == "INVALID_ALLOCATION_CONFIGURATION"
    assert "costs.items[shared_b].allocation_rule" in warning["dependency_paths"]
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 16. explicit zero rate does not block computation (TC16)
# ---------------------------------------------------------------------------
def test_16_explicit_zero_rate_is_not_unknown():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     net_sales_fee_rate=0.0, gross_payment_fee_rate=0.05)
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 64500)


# ---------------------------------------------------------------------------
# 17. no variable-cost items at all -> confirmed 0, not UNKNOWN (TC17)
# ---------------------------------------------------------------------------
def test_17_no_variable_cost_items_confirmed_zero():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3)
    assert ci["costs"]["items"] == []
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 70000)


# ---------------------------------------------------------------------------
# 18. matching variable-cost item exists but its value is null -> UNKNOWN (TC18)
# ---------------------------------------------------------------------------
def test_18_matching_variable_item_null_value_is_unknown():
    ci = make_input(
        price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "b_null", "label": "b", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": None, "currency": None, "basis": "rate_of_net_sales",
            "applies_to_component": "main",
        }],
    )
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "UNKNOWN"
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_c.per_component.main.allowable_direct_cost")
    assert "costs.items[b_null].rate" in warning["dependency_paths"]


# ---------------------------------------------------------------------------
# 19. actual_direct_cost UNKNOWN (item exists, amount null) -> ADC OK, gap UNKNOWN (TC19)
# ---------------------------------------------------------------------------
def test_19_actual_direct_cost_unknown_adc_unaffected():
    ci = make_input(
        price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "direct_null", "label": "직접원가", "cost_category": "product_service_direct_cost",
            "amount": None, "rate": None, "currency": "KRW", "basis": "per_unit",
            "applies_to_component": "main",
        }],
    )
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 70000)
    actual = m(result, "actual_direct_cost")
    assert actual["status"] == "UNKNOWN"
    gap = m(result, "direct_cost_gap")
    assert gap["status"] == "UNKNOWN"
    cm = m(result, "expected_contribution_margin")
    assert cm["status"] == "OK"
    cmr = m(result, "expected_contribution_margin_rate")
    assert cmr["status"] == "OK"
    assert approx(cmr["value"], 0.3)


# ---------------------------------------------------------------------------
# 20. shared product_service_direct_cost unresolved -> ADC OK, actual/gap UNKNOWN (TC20)
# ---------------------------------------------------------------------------
def test_20_shared_direct_cost_unresolved_adc_unaffected():
    ci = make_input(
        price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "shared_direct", "label": "공유 직접원가", "cost_category": "product_service_direct_cost",
            "amount": 1000, "rate": None, "currency": "KRW", "basis": "per_unit",
            "applies_to_component": "shared", "allocation_rule": "by_component_revenue",
        }],
    )
    result = run_mode_c(ci)
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "OK"
    assert approx(adc["value"], 70000)
    actual = m(result, "actual_direct_cost")
    assert actual["status"] == "UNKNOWN"
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_c.per_component.main.actual_direct_cost")
    assert warning["code"] == "UNSUPPORTED_SHARED_COST_ALLOCATION"
    gap = m(result, "direct_cost_gap")
    assert gap["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 21-22 — module status must pool metrics across ALL components, not just the last one
# iterated, and the result must not depend on component list order (mirrors MODE A/B's own
# regression tests for this exact pattern).
# ---------------------------------------------------------------------------
def _two_component_ci(order):
    # "err" is scoped to fail on its own (unsupported currency -> ERROR on market_net_sales_ex_vat
    # -> ERROR on allowable_direct_cost) WITHOUT using a "shared" cost item -- a shared item would
    # affect every component in the product, not just this one, which would defeat the purpose of
    # this order-independence test (isolating ERROR to exactly one component).
    err_component = {"component_id": "err", "type": "one_time", "actual_price": None,
                      "currency": "EUR", "price_includes_vat": False, "target_market_price": 100000}
    ok_component = {"component_id": "ok", "type": "one_time", "actual_price": None,
                     "currency": "KRW", "price_includes_vat": False, "target_market_price": 100000}

    components_and_items = {"err": (err_component, []), "ok": (ok_component, [])}
    price_components = [components_and_items[cid][0] for cid in order]
    items = [item for cid in order for item in components_and_items[cid][1]]
    return {
        "schema_version": "1.1", "client_id": "x", "case_id": "y",
        "product": {"name": "n", "pricing_model": "hybrid", "price_components": price_components},
        "tax": {"vat_rate": 0.10},
        "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": 0.3},
        "meta": {},
    }


def test_21_module_status_error_pooled_err_first():
    ci = _two_component_ci(order=["err", "ok"])
    result = run_mode_c(ci)
    assert result["per_component"]["err"]["allowable_direct_cost"]["status"] == "ERROR"
    assert result["per_component"]["ok"]["allowable_direct_cost"]["status"] == "OK"
    assert result["status"] == "ERROR"


def test_22_module_status_error_pooled_ok_first():
    # same scenario, component order reversed -> result must be identical (order-independent)
    ci = _two_component_ci(order=["ok", "err"])
    result = run_mode_c(ci)
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 23 — N=0 ratio semantics: a confirmed-zero market price makes the CM rate a genuine
# division-by-zero ERROR, not silently 0% and not UNKNOWN.
# ---------------------------------------------------------------------------
def test_23_zero_market_price_makes_cmr_calculation_error():
    ci = make_input(price=0, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3)
    result = run_mode_c(ci)
    n = m(result, "market_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert n["value"] == 0
    cmr = m(result, "expected_contribution_margin_rate")
    assert cmr["status"] == "ERROR"
    assert cmr["value"] is None


# ---------------------------------------------------------------------------
# 24 — unsupported currency conversion -> ERROR, not UNKNOWN
# ---------------------------------------------------------------------------
def test_24_unsupported_currency_is_error():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     currency="EUR")
    # fx only supports base_currency (KRW) <-> reporting_currency (KRW); EUR is neither
    ci["fx"] = {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1}
    result = run_mode_c(ci)
    n = m(result, "market_net_sales_ex_vat")
    assert n["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 25 — price missing entirely (target_market_price = null) -> UNKNOWN, not a crash
# ---------------------------------------------------------------------------
def test_25_missing_market_price_is_unknown():
    ci = make_input(price=None, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
                     price_is_null=True)
    result = run_mode_c(ci)
    n = m(result, "market_net_sales_ex_vat")
    assert n["status"] == "UNKNOWN"
    assert "product.price_components[main].target_market_price" in \
        next(w for w in result["warnings"]
             if w["metric_path"] == "mode_c.per_component.main.market_net_sales_ex_vat")["dependency_paths"]
    adc = m(result, "allowable_direct_cost")
    assert adc["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 26 — result_builder wiring: mode_c block appears with the expected shape.
# ---------------------------------------------------------------------------
def test_26_result_builder_includes_mode_c():
    ci = make_input(price=100000, price_includes_vat=False, vat_rate=0.10, target_cm_rate=0.3)
    analysis_result = build_analysis_result(ci, client_input_ref="test")
    assert analysis_result["mode_c"]["status"] == "OK"
    adc = analysis_result["mode_c"]["per_component"]["main"]["allowable_direct_cost"]
    assert adc["status"] == "OK"
    assert approx(adc["value"], 70000)


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
