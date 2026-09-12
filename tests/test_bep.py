# -*- coding: utf-8 -*-
"""
Unit tests for BEP (core/engine/modes/bep.py).

Every numeric expectation here is hand-checked against docs/features/bep/CASE.md (TC1-TC23) —
this file's test numbers are labeled with which CASE.md TC they match. Fixtures are intentionally
minimal and independent from core/schemas/examples/ (which exist to demonstrate the schema, not
pin exact engine outputs).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.modes.bep import run_bep  # noqa: E402
from core.engine.modes.mode_a import run_mode_a  # noqa: E402
from core.engine.result_builder import build_analysis_result  # noqa: E402
from core.engine.validation.validate_client_input import assert_valid_client_input  # noqa: E402

APPROX = 1e-4


def approx(a, b, tol=APPROX):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def make_input(*, actual_price, price_includes_vat, vat_rate, items,
                target_cm_rate=None, extra_components=None, currency="KRW"):
    """Builds a Client Input for BEP with full control over costs.items (BEP needs precise
    control over fixed_operating_cost item shape that a narrower category-rate builder can't
    express). `items` is a list of raw cost_item dicts (item_id/label/cost_category/amount/rate/
    currency/basis/applies_to_component[/allocation_rule]) for the "main" component.
    `extra_components` optionally adds more price_components (for the multi-component gate
    tests) — each a dict merged over the default one_time-component shape."""
    components = [{
        "component_id": "main", "type": "one_time", "actual_price": actual_price,
        "currency": currency, "price_includes_vat": price_includes_vat,
    }]
    if extra_components:
        components.extend(extra_components)
    return {
        "schema_version": "1.1", "client_id": "unit_test_co", "case_id": "unit_test_case_bep",
        "product": {"name": "bep_test", "pricing_model": "one_time", "price_components": components},
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": currency, "reporting_currency": currency, "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": target_cm_rate},
        "meta": {},
    }


def direct_item(amount, component_id="main", currency="KRW"):
    return {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
            "amount": amount, "rate": None, "currency": currency, "basis": "per_unit",
            "applies_to_component": component_id}


def variable_fixed_item(amount, item_id="var_fixed", component_id="main", currency="KRW"):
    return {"item_id": item_id, "label": "변동비(금액)", "cost_category": "variable_selling_delivery",
            "amount": amount, "rate": None, "currency": currency, "basis": "per_order",
            "applies_to_component": component_id}


def variable_rate_item(rate, basis, item_id="var_rate", component_id="main"):
    return {"item_id": item_id, "label": "변동비(비율)", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": rate, "currency": None, "basis": basis,
            "applies_to_component": component_id}


def fc_item(amount, basis="per_month", item_id="fc", component_id="main", currency="KRW",
            applies_to_component=None, allocation_rule=None):
    return {"item_id": item_id, "label": "고정운영비", "cost_category": "fixed_operating_cost",
            "amount": amount, "rate": None, "currency": currency, "basis": basis,
            "applies_to_component": applies_to_component or component_id,
            **({"allocation_rule": allocation_rule} if allocation_rule else {})}


def m(client_input):
    """Runs BEP and returns the (validated) single component's metrics dict + module status."""
    assert_valid_client_input(client_input)
    result = run_bep(client_input)
    return result


# TC1 — simple positive CM ---------------------------------------------------------------------
def test_01_simple_positive_cm():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000),
    ])
    r = m(ci)
    assert r["status"] == "OK"
    c = r["per_component"]["main"]
    assert c["contribution_margin_per_unit"]["status"] == "OK"
    assert approx(c["contribution_margin_per_unit"]["value"], 500)
    assert c["fixed_operating_cost"]["status"] == "OK"
    assert approx(c["fixed_operating_cost"]["value"], 50000)
    assert c["break_even_quantity_exact"]["status"] == "OK"
    assert approx(c["break_even_quantity_exact"]["value"], 100)
    assert c["analysis_period_basis"] == "per_month"


# TC2 — fixed cost = 0 (explicit) --------------------------------------------------------------
def test_02_fixed_cost_zero_explicit():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(0),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "OK"
    assert c["fixed_operating_cost"]["value"] == 0
    assert c["break_even_quantity_exact"]["status"] == "OK"
    assert c["break_even_quantity_exact"]["value"] == 0
    assert c["analysis_period_basis"] == "per_month"


# TC3 — no fixed-cost item at all (confirmed 0, contrast with TC2) ----------------------------
def test_03_no_fixed_cost_item_at_all():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "OK"
    assert c["fixed_operating_cost"]["value"] == 0
    assert c["break_even_quantity_exact"]["value"] == 0
    assert c["analysis_period_basis"] is None
    assert r["status"] == "OK"


# TC4 — fixed-cost item exists but amount = null -----------------------------------------------
def test_04_fixed_cost_item_amount_null():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(None),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "UNKNOWN"
    assert c["break_even_quantity_exact"]["status"] == "UNKNOWN"
    assert r["status"] == "INCOMPLETE"


# TC5 — CM = 0, FC > 0 ---------------------------------------------------------------------------
def test_05_cm_zero_fc_positive():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(600), variable_fixed_item(400), fc_item(50000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["contribution_margin_per_unit"]["status"] == "OK"
    assert c["contribution_margin_per_unit"]["value"] == 0
    q = c["break_even_quantity_exact"]
    assert q["status"] == "NOT_APPLICABLE"
    assert q["value"] is None
    assert any(w["code"] == "BREAK_EVEN_UNDEFINED_ZERO_MARGIN" for w in r["warnings"])
    assert r["status"] == "OK"


# TC6 — CM < 0, FC > 0 ---------------------------------------------------------------------------
def test_06_cm_negative_fc_positive():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(700), variable_fixed_item(400), fc_item(50000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], -100)
    q = c["break_even_quantity_exact"]
    assert q["status"] == "NOT_APPLICABLE"
    assert q["value"] is None
    assert any(w["code"] == "BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN" for w in r["warnings"])
    assert r["status"] == "OK"


# TC7 — VAT-inclusive display price --------------------------------------------------------------
def test_07_vat_inclusive_display():
    ci = make_input(actual_price=1100, price_includes_vat=True, vat_rate=0.10, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], 500)
    assert approx(c["break_even_quantity_exact"]["value"], 100)


# TC8 — VAT-exclusive display, same underlying economics as TC7 -----------------------------------
def test_08_vat_exclusive_display_same_economics():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=0.10, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], 500)
    assert approx(c["break_even_quantity_exact"]["value"], 100)


# TC9 — net-sales fee ------------------------------------------------------------------------------
def test_09_net_sales_fee():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(200), variable_rate_item(0.1, "rate_of_net_sales"), fc_item(70000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], 700)
    assert approx(c["break_even_quantity_exact"]["value"], 100)


# TC10 — gross-payment fee -------------------------------------------------------------------------
def test_10_gross_payment_fee():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=0.10, items=[
        direct_item(0), variable_rate_item(0.05, "rate_of_gross_payment"), fc_item(94500),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], 945)
    assert approx(c["break_even_quantity_exact"]["value"], 100)


# TC11 — v UNKNOWN but not needed (a=0, price_includes_vat=false) -----------------------------------
def test_11_v_unknown_not_needed():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(300), variable_rate_item(0.1, "rate_of_net_sales"), fc_item(60000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], 600)
    assert approx(c["break_even_quantity_exact"]["value"], 100)
    assert r["status"] == "OK"


# TC12 — v UNKNOWN and actually required -------------------------------------------------------------
def test_12_v_unknown_required():
    ci = make_input(actual_price=1100, price_includes_vat=True, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["contribution_margin_per_unit"]["status"] == "UNKNOWN"
    assert c["break_even_quantity_exact"]["status"] == "UNKNOWN"
    assert r["status"] == "INCOMPLETE"


# TC13 — unsupported currency on the fixed-cost item ---------------------------------------------------
def test_13_unsupported_currency_on_fc_item():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000, currency="EUR"),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "ERROR"
    assert any(w["code"] == "UNSUPPORTED_CURRENCY" for w in r["warnings"])
    assert c["break_even_quantity_exact"]["status"] == "ERROR"
    assert r["status"] == "ERROR"


# TC14 — shared fixed cost, unresolved allocation -------------------------------------------------------
def test_14_shared_fixed_cost_unresolved():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100),
        fc_item(None, applies_to_component="shared", allocation_rule="by_component_revenue"),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "UNKNOWN"
    assert any(w["code"] == "UNSUPPORTED_SHARED_COST_ALLOCATION" for w in r["warnings"])
    assert c["break_even_quantity_exact"]["status"] == "UNKNOWN"


# TC15 — shared + direct invalid configuration -----------------------------------------------------------
def test_15_shared_plus_direct_invalid():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100),
        fc_item(None, applies_to_component="shared", allocation_rule="direct"),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "ERROR"
    assert any(w["code"] == "INVALID_ALLOCATION_CONFIGURATION" for w in r["warnings"])
    assert c["break_even_quantity_exact"]["status"] == "ERROR"
    assert r["status"] == "ERROR"


# TC16 — explicit zero rate does not block computation -----------------------------------------------------
def test_16_explicit_zero_rate():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=0.10, items=[
        direct_item(400), variable_rate_item(0, "rate_of_net_sales"), fc_item(60000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], 600)
    assert approx(c["break_even_quantity_exact"]["value"], 100)


# TC17 — non-integer break-even quantity ---------------------------------------------------------------------
def test_17_non_integer_quantity():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(52340),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["break_even_quantity_exact"]["value"], 104.68)
    # v0.1 never produces a rounded/units metric — only the 4 required keys exist.
    assert set(c.keys()) == {
        "analysis_period_basis", "contribution_margin_per_unit",
        "fixed_operating_cost", "break_even_quantity_exact",
    }


# TC18 — multi-component input, component-specific fixed costs (BEP v0.1 refuses) ------------------------------
def test_18_multi_component_component_specific_fc_refused():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000),
        fc_item(20000, item_id="fc_addon", component_id="addon"),
    ], extra_components=[{
        "component_id": "addon", "type": "one_time", "actual_price": 500,
        "currency": "KRW", "price_includes_vat": False,
    }])
    r = m(ci)
    assert r["status"] == "ERROR"
    assert r["per_component"] == {}
    assert len(r["warnings"]) == 1
    assert r["warnings"][0]["code"] == "MULTI_COMPONENT_BEP_NOT_SUPPORTED"


# TC19 — multi-component input, with a shared fixed cost (motivating case) --------------------------------------
def test_19_multi_component_with_shared_fc_still_refused():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000),
        fc_item(20000, item_id="fc_addon", component_id="addon"),
        fc_item(8000000, item_id="fc_shared", applies_to_component="shared", allocation_rule="blended_only"),
    ], extra_components=[{
        "component_id": "addon", "type": "one_time", "actual_price": 500,
        "currency": "KRW", "price_includes_vat": False,
    }])
    r = m(ci)
    assert r["status"] == "ERROR"
    assert r["per_component"] == {}
    assert len(r["warnings"]) == 1
    assert r["warnings"][0]["code"] == "MULTI_COMPONENT_BEP_NOT_SUPPORTED"


# TC20 — CM input UNKNOWN (direct cost missing), FC unaffected -----------------------------------------------------
def test_20_cm_input_unknown_fc_isolated():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(None), variable_fixed_item(100), fc_item(50000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["contribution_margin_per_unit"]["status"] == "UNKNOWN"
    assert c["fixed_operating_cost"]["status"] == "OK"
    assert approx(c["fixed_operating_cost"]["value"], 50000)
    assert c["break_even_quantity_exact"]["status"] == "UNKNOWN"
    assert r["status"] == "INCOMPLETE"


# TC21 — FC = 0, CM = 0 (both terms simultaneously zero — distinct warning) -----------------------------------------
def test_21_fc_zero_cm_zero():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(600), variable_fixed_item(400), fc_item(0),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["contribution_margin_per_unit"]["value"] == 0
    assert c["fixed_operating_cost"]["value"] == 0
    q = c["break_even_quantity_exact"]
    assert q["status"] == "NOT_APPLICABLE"
    assert q["value"] is None
    assert any(w["code"] == "BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST" for w in r["warnings"])


# TC22 — FC = 0, CM < 0 (raw arithmetic gives 0, must still be NOT_APPLICABLE) ----------------------------------------
def test_22_fc_zero_cm_negative():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(700), variable_fixed_item(400), fc_item(0),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert approx(c["contribution_margin_per_unit"]["value"], -100)
    assert c["fixed_operating_cost"]["value"] == 0
    q = c["break_even_quantity_exact"]
    assert q["status"] == "NOT_APPLICABLE"
    assert q["value"] is None
    assert any(w["code"] == "BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN" for w in r["warnings"])


# TC23 — negative fixed_operating_cost amount ------------------------------------------------------------------------
def test_23_negative_fixed_cost_amount():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(-10000),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "ERROR"
    assert any(w["code"] == "INVALID_NEGATIVE_COST" for w in r["warnings"])
    assert c["break_even_quantity_exact"]["status"] == "ERROR"
    assert r["status"] == "ERROR"


# ------------------------------------------------------------------------------------------------------------------
# Additional cross-cutting tests (item 14 of the implementation request)
# ------------------------------------------------------------------------------------------------------------------

def test_multi_component_gate_beats_other_errors():
    """A multi-component input that ALSO has an inconsistent fixed-cost basis must report only
    MULTI_COMPONENT_BEP_NOT_SUPPORTED — INCONSISTENT_FIXED_COST_BASIS must never be evaluated or
    appear (dependency_rules.md section 7's STEP 1/STEP 2 ordering)."""
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100),
        fc_item(50000, basis="per_month", item_id="fc1"),
        fc_item(20000, basis="per_visit", item_id="fc2"),
    ], extra_components=[{
        "component_id": "addon", "type": "one_time", "actual_price": 500,
        "currency": "KRW", "price_includes_vat": False,
    }])
    r = m(ci)
    assert r["status"] == "ERROR"
    assert r["per_component"] == {}
    codes = {w["code"] for w in r["warnings"]}
    assert codes == {"MULTI_COMPONENT_BEP_NOT_SUPPORTED"}


def test_inconsistent_fixed_cost_basis():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100),
        fc_item(50000, basis="per_month", item_id="fc1"),
        fc_item(20000, basis="per_visit", item_id="fc2"),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["fixed_operating_cost"]["status"] == "ERROR"
    assert any(w["code"] == "INCONSISTENT_FIXED_COST_BASIS" for w in r["warnings"])
    assert r["status"] == "ERROR"


def test_not_applicable_keeps_module_status_ok():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(700), variable_fixed_item(400), fc_item(50000),
    ])
    r = m(ci)
    assert r["per_component"]["main"]["break_even_quantity_exact"]["status"] == "NOT_APPLICABLE"
    assert r["status"] == "OK"


def test_error_beats_unknown_beats_not_applicable_priority():
    """A single component can't simultaneously be all three, but this pins the aggregate rule
    directly: ERROR present anywhere -> module ERROR, matching common.aggregate_module_status()."""
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(-1),
    ])
    r = m(ci)
    assert r["status"] == "ERROR"


def test_analysis_period_basis_consistent_items():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100),
        fc_item(30000, basis="per_month", item_id="fc1"),
        fc_item(20000, basis="per_month", item_id="fc2"),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["analysis_period_basis"] == "per_month"
    assert approx(c["fixed_operating_cost"]["value"], 50000)


def test_no_fc_item_basis_null_and_fc_zero():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100),
    ])
    r = m(ci)
    c = r["per_component"]["main"]
    assert c["analysis_period_basis"] is None
    assert c["fixed_operating_cost"]["value"] == 0
    assert c["fixed_operating_cost"]["status"] == "OK"


# ------------------------------------------------------------------------------------------------------------------
# result_builder / schema integration
# ------------------------------------------------------------------------------------------------------------------

def test_cross_mode_cm_parity_with_mode_a():
    """MODE A's contribution_margin and BEP's contribution_margin_per_unit must agree exactly
    for the same single-component Client Input (both now call the same core/engine/economics.py
    primitives) — VAT-inclusive display, both a rate_of_net_sales and a rate_of_gross_payment
    fee present, so both the N and G paths are exercised."""
    ci = make_input(actual_price=13200, price_includes_vat=True, vat_rate=0.10, items=[
        direct_item(4000),
        variable_rate_item(0.05, "rate_of_net_sales"),
        variable_rate_item(0.02, "rate_of_gross_payment"),
        fc_item(1000000),
    ])
    mode_a_result = run_mode_a(ci)
    bep_result = run_bep(ci)

    mode_a_cm = mode_a_result["per_component"]["main"]["contribution_margin"]
    bep_cmu = bep_result["per_component"]["main"]["contribution_margin_per_unit"]

    assert mode_a_cm["status"] == "OK"
    assert bep_cmu["status"] == "OK"
    assert approx(mode_a_cm["value"], bep_cmu["value"])
    assert mode_a_cm["unit"] == bep_cmu["unit"]


def test_result_builder_includes_bep_block():
    ci = make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
        direct_item(400), variable_fixed_item(100), fc_item(50000),
    ])
    assert_valid_client_input(ci)
    result = build_analysis_result(ci, "test")
    assert result["bep"]["status"] == "OK"
    assert approx(result["bep"]["per_component"]["main"]["break_even_quantity_exact"]["value"], 100)


def test_bep_warnings_never_reference_mode_a_namespace():
    """BEP now shares core/engine/economics.py primitives with MODE A but must never leak a
    mode_a.per_component... metric_path/dependency_path into its own warnings — only bep.* or
    raw client_input paths are valid. Exercises every dependency-missing shape economics.py's
    sum_cost_category can produce."""
    scenarios = [
        make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
            direct_item(None), variable_fixed_item(100), fc_item(50000),
        ]),
        make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
            direct_item(400), variable_rate_item(None, "rate_of_net_sales"), fc_item(50000),
        ]),
        make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
            direct_item(400, currency="EUR"), variable_fixed_item(100), fc_item(50000),
        ]),
        make_input(actual_price=1000, price_includes_vat=False, vat_rate=None, items=[
            direct_item(400),
            {"item_id": "sv", "label": "sv", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": None, "currency": None, "basis": "per_order",
             "applies_to_component": "shared", "allocation_rule": "by_component_revenue"},
            fc_item(50000),
        ]),
    ]
    for ci in scenarios:
        r = m(ci)
        for w in r["warnings"]:
            assert not w["metric_path"].startswith("mode_a."), w
            for dep in w["dependency_paths"]:
                assert not dep.startswith("mode_a."), (w, dep)
