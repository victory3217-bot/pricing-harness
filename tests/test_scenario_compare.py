# -*- coding: utf-8 -*-
"""
Unit tests for Scenario Compare (core/engine/scenario_compare.py).

Numeric expectations are hand-checked against docs/features/scenario_compare/CASE.md — test
names are labeled with which CASE.md TC they match where applicable. Not every one of CASE.md's
37 cases gets its own test (several are narrative variations of the same mechanical behavior);
this file instead covers every distinct *mechanism* CASE.md exercises.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.scenario_compare import run_scenario_compare  # noqa: E402
from core.engine.validation.validate_scenario_compare import (  # noqa: E402
    validate_scenario_compare_request,
    validate_scenario_compare_result,
)

APPROX = 1e-4


def approx(a, b, tol=APPROX):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def make_base_input(*, actual_price=1000, price_includes_vat=False, vat_rate=0.10,
                     direct_amount=400, var_fixed_amount=100, net_sales_rate=0, gross_payment_rate=0,
                     fc_amount=50000, fc_basis="per_month", target_market_price=1000,
                     target_cm_rate=0.3, currency="KRW", extra_components=None, extra_items=None):
    items = [
        {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
         "amount": direct_amount, "rate": None, "currency": currency, "basis": "per_unit",
         "applies_to_component": "main"},
        {"item_id": "var_fixed", "label": "변동비", "cost_category": "variable_selling_delivery",
         "amount": var_fixed_amount, "rate": None, "currency": currency, "basis": "per_order",
         "applies_to_component": "main"},
        {"item_id": "var_net_sales", "label": "매출액기준", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": net_sales_rate, "currency": None, "basis": "rate_of_net_sales",
         "applies_to_component": "main"},
        {"item_id": "var_gross_payment", "label": "결제액기준", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": gross_payment_rate, "currency": None, "basis": "rate_of_gross_payment",
         "applies_to_component": "main"},
        {"item_id": "fixed_ops", "label": "고정운영비", "cost_category": "fixed_operating_cost",
         "amount": fc_amount, "rate": None, "currency": currency, "basis": fc_basis,
         "applies_to_component": "main"},
    ]
    if extra_items:
        items.extend(extra_items)
    components = [{
        "component_id": "main", "type": "one_time", "actual_price": actual_price,
        "target_market_price": target_market_price, "currency": currency,
        "price_includes_vat": price_includes_vat, "discount_rate": 0,
    }]
    if extra_components:
        components.extend(extra_components)
    return {
        "schema_version": "1.1", "client_id": "sc_test_co", "case_id": "sc_test_case",
        "product": {"name": "sc_test", "pricing_model": "one_time", "price_components": components},
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": currency, "reporting_currency": currency, "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": target_cm_rate},
        "meta": {},
    }


def make_request(base_input, scenarios, baseline_scenario_id="A"):
    return {"base_input": base_input, "baseline_scenario_id": baseline_scenario_id, "scenarios": scenarios}


def scenario(sid, label="", overrides=None):
    d = {"scenario_id": sid, "label": label}
    if overrides is not None:
        d["overrides"] = overrides
    return d


# ---------------------------------------------------------------------------
# TC1-12 — arithmetic pass-through, deltas
# ---------------------------------------------------------------------------

def test_tc1_baseline_no_overrides():
    base = make_base_input()
    req = make_request(base, [scenario("A", "baseline"), scenario("B", "other", {"components": [{"component_id": "main", "actual_price": 1200}]})])
    result = run_scenario_compare(req)
    assert result["status"] == "OK"
    a = result["scenarios"][0]
    assert a["scenario_status"] == "OK"
    comp = a["summary"]["per_component"]["main"]
    assert approx(comp["mode_a"]["contribution_margin"]["value"], 500)
    assert approx(comp["bep"]["break_even_quantity_exact"]["value"], 100)
    d = a["deltas"]["per_component"]["main"]
    assert d["contribution_margin_delta"] == {"value": 0, "status": "OK"}
    assert d["break_even_quantity_delta"] == {"value": 0, "status": "OK"}


def test_tc2_price_increase():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]})])
    result = run_scenario_compare(req)
    b = result["scenarios"][1]
    comp = b["summary"]["per_component"]["main"]
    assert approx(comp["mode_a"]["contribution_margin"]["value"], 700)
    assert approx(comp["bep"]["break_even_quantity_exact"]["value"], 71.42857)
    d = b["deltas"]["per_component"]["main"]
    assert approx(d["net_sales_ex_vat_delta"]["value"], 200)
    assert approx(d["contribution_margin_delta"]["value"], 200)
    assert d["break_even_quantity_delta"]["value"] < 0  # BEP improves


def test_tc3_price_decrease_bep_worsens():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("C", overrides={"components": [{"component_id": "main", "actual_price": 800}]})])
    result = run_scenario_compare(req)
    c = result["scenarios"][1]
    d = c["deltas"]["per_component"]["main"]
    assert approx(d["contribution_margin_delta"]["value"], -200)
    assert d["break_even_quantity_delta"]["value"] > 0  # BEP worsens


def test_tc4_direct_cost_reduction():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("D", overrides={"cost_items": [{"item_id": "direct", "amount": 300}]})])
    result = run_scenario_compare(req)
    d_entry = result["scenarios"][1]
    comp = d_entry["summary"]["per_component"]["main"]
    assert approx(comp["mode_a"]["contribution_margin"]["value"], 600)
    # ADC = N(1-t-b) - aG - F = 1000*0.7 - 100(var_fixed=F) = 600; actual_direct_cost=300 -> gap=300
    assert approx(comp["mode_c"]["direct_cost_gap"]["value"], 300)


def test_tc6_target_cm_increase_isolated_to_mode_b_c():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("F", overrides={"targets": {"target_contribution_margin_rate": 0.5}})])
    result = run_scenario_compare(req)
    f = result["scenarios"][1]
    d = f["deltas"]["per_component"]["main"]
    assert d["contribution_margin_delta"]["value"] == 0
    assert d["break_even_quantity_delta"]["value"] == 0
    comp = f["summary"]["per_component"]["main"]
    # MODE B's C = direct(400) + fixed-amount variable(100) = 500; D = 1-0.5 = 0.5 -> N = 1000
    assert approx(comp["mode_b"]["required_selling_price"]["value"], 1000)


def test_tc9_negative_allowable_cost_reuses_mode_c_case_tc11():
    base = make_base_input(target_market_price=10000, target_cm_rate=0.5, net_sales_rate=0.3,
                            gross_payment_rate=0.3, vat_rate=0.10, var_fixed_amount=0)
    req = make_request(base, [scenario("A"), scenario("I", overrides={"components": [{"component_id": "main", "actual_price": 10000}]})])
    result = run_scenario_compare(req)
    a = result["scenarios"][0]
    comp = a["summary"]["per_component"]["main"]
    assert approx(comp["mode_c"]["allowable_direct_cost"]["value"], -1300)
    assert comp["mode_c"]["status"] == "OK"
    # MODE C's ADC stays OK (with its own non-blocking NEGATIVE_ALLOWABLE_COST warning) even
    # though the SAME b=0.3/a=0.3 cost items independently push MODE B's own denominator <= 0
    # (D = 1-0.5-0.3-0.3*1.1 = -0.13) -> mode_b ERROR -> scenario_status ERROR overall. This is
    # correct, expected cross-mode behavior (all four modes share the same cost items), not a
    # dependency-isolation violation within MODE C itself.
    assert a["results"]["mode_b"]["status"] == "ERROR"
    assert a["scenario_status"] == "ERROR"


def test_tc12_fixed_cost_increase_isolated_to_bep():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("L", overrides={"cost_items": [{"item_id": "fixed_ops", "amount": 80000}]})])
    result = run_scenario_compare(req)
    l_entry = result["scenarios"][1]
    d = l_entry["deltas"]["per_component"]["main"]
    assert d["contribution_margin_delta"]["value"] == 0
    assert approx(d["break_even_quantity_delta"]["value"], 60)


# ---------------------------------------------------------------------------
# TC13/34 — VAT display comparability via net_sales_ex_vat_delta
# ---------------------------------------------------------------------------

def test_tc13_tc34_vat_display_comparison_uses_net_sales_delta():
    base = make_base_input(actual_price=1000, price_includes_vat=False)
    m2 = copy.deepcopy(base)
    req = make_request(base, [
        scenario("M1"),
        scenario("M2", overrides={"components": [{"component_id": "main", "actual_price": 1100, "price_includes_vat": True}]}),
    ], baseline_scenario_id="M1")
    result = run_scenario_compare(req)
    m2_entry = result["scenarios"][1]
    d = m2_entry["deltas"]["per_component"]["main"]
    assert approx(d["net_sales_ex_vat_delta"]["value"], 0)
    assert d["net_sales_ex_vat_delta"]["status"] == "OK"


# ---------------------------------------------------------------------------
# TC14/TC16 — UNKNOWN input, TC15 — ERROR scenario
# ---------------------------------------------------------------------------

def test_tc14_unknown_input_propagates():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("N", overrides={
        "components": [{"component_id": "main", "price_includes_vat": True}],
        "tax": {"vat_rate": None},
    })])
    result = run_scenario_compare(req)
    n = result["scenarios"][1]
    assert n["scenario_status"] == "INCOMPLETE"
    comp = n["summary"]["per_component"]["main"]
    assert comp["mode_a"]["contribution_margin"]["status"] == "UNKNOWN"
    d = n["deltas"]["per_component"]["main"]
    assert d["contribution_margin_delta"]["status"] == "UNKNOWN"


def test_tc15_error_scenario_others_unaffected():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("O", overrides={"cost_items": [{"item_id": "fixed_ops", "amount": -10000}]})])
    result = run_scenario_compare(req)
    o = result["scenarios"][1]
    assert o["scenario_status"] == "ERROR"
    assert result["scenarios"][0]["scenario_status"] == "OK"
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# TC16(BEP) — NOT_APPLICABLE BEP keeps scenario OK
# ---------------------------------------------------------------------------

def test_tc16_bep_not_applicable_keeps_scenario_ok():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("P", overrides={"components": [{"component_id": "main", "actual_price": 500}]})])
    result = run_scenario_compare(req)
    p = result["scenarios"][1]
    comp = p["summary"]["per_component"]["main"]
    assert comp["mode_a"]["contribution_margin"]["value"] == 0
    assert comp["bep"]["break_even_quantity_exact"]["status"] == "NOT_APPLICABLE"
    assert comp["bep"]["status"] == "OK"
    assert p["scenario_status"] == "OK"
    d = p["deltas"]["per_component"]["main"]
    assert d["break_even_quantity_delta"]["status"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# TC17/18 — shared variable/fixed cost unresolved
# ---------------------------------------------------------------------------

def test_tc17_shared_variable_unresolved():
    base = make_base_input(net_sales_rate=None)
    base["costs"]["items"] = [it for it in base["costs"]["items"] if it["item_id"] != "var_net_sales"]
    base["costs"]["items"].append({
        "item_id": "shared_var", "label": "공유변동비", "cost_category": "variable_selling_delivery",
        "amount": None, "rate": None, "currency": None, "basis": "rate_of_net_sales",
        "applies_to_component": "shared", "allocation_rule": "by_component_revenue",
    })
    req = make_request(base, [scenario("A"), scenario("Q", overrides={"components": [{"component_id": "main", "actual_price": 1100}]})])
    result = run_scenario_compare(req)
    a = result["scenarios"][0]
    comp = a["summary"]["per_component"]["main"]
    assert comp["mode_a"]["contribution_margin"]["status"] == "UNKNOWN"
    assert comp["bep"]["contribution_margin_per_unit"]["status"] == "UNKNOWN"
    assert a["scenario_status"] == "INCOMPLETE"


def test_tc18_shared_fixed_unresolved():
    base = make_base_input()
    base["costs"]["items"] = [it for it in base["costs"]["items"] if it["item_id"] != "fixed_ops"]
    base["costs"]["items"].append({
        "item_id": "shared_fc", "label": "공유고정비", "cost_category": "fixed_operating_cost",
        "amount": None, "rate": None, "currency": None, "basis": "per_month",
        "applies_to_component": "shared", "allocation_rule": "blended_only",
    })
    req = make_request(base, [scenario("A"), scenario("R", overrides={"components": [{"component_id": "main", "actual_price": 1100}]})])
    result = run_scenario_compare(req)
    a = result["scenarios"][0]
    comp = a["summary"]["per_component"]["main"]
    assert comp["mode_a"]["status"] == "OK"  # unaffected
    assert comp["bep"]["fixed_operating_cost"]["status"] == "UNKNOWN"
    assert a["scenario_status"] == "INCOMPLETE"


# ---------------------------------------------------------------------------
# TC19 — multi-component -> BEP ERROR only
# ---------------------------------------------------------------------------

def test_tc19_multi_component_bep_error_only():
    base = make_base_input(extra_components=[{
        "component_id": "addon", "type": "one_time", "actual_price": 500,
        "currency": "KRW", "price_includes_vat": False,
    }])
    req = make_request(base, [scenario("A"), scenario("S", overrides={"components": [{"component_id": "main", "actual_price": 1100}]})])
    result = run_scenario_compare(req)
    a = result["scenarios"][0]
    assert a["results"]["mode_a"]["status"] == "OK"
    assert a["results"]["bep"]["status"] == "ERROR"
    assert any(w["code"] == "MULTI_COMPONENT_BEP_NOT_SUPPORTED" for w in a["results"]["bep"]["warnings"])
    assert a["scenario_status"] == "ERROR"
    # bep summary is None for every component since bep.per_component is {}
    assert a["summary"]["per_component"]["main"]["bep"] is None
    assert a["summary"]["per_component"]["addon"]["bep"] is None


# ---------------------------------------------------------------------------
# TC20 — baseline change affects delta reference
# ---------------------------------------------------------------------------

def test_tc20_baseline_change_recomputes_deltas():
    base = make_base_input()
    scenarios = [
        scenario("A"),
        scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]}),
        scenario("C", overrides={"components": [{"component_id": "main", "actual_price": 800}]}),
    ]
    result_a_baseline = run_scenario_compare(make_request(base, scenarios, baseline_scenario_id="A"))
    result_c_baseline = run_scenario_compare(make_request(base, scenarios, baseline_scenario_id="C"))
    b_vs_a = result_a_baseline["scenarios"][1]["deltas"]["per_component"]["main"]["net_sales_ex_vat_delta"]["value"]
    b_vs_c = result_c_baseline["scenarios"][1]["deltas"]["per_component"]["main"]["net_sales_ex_vat_delta"]["value"]
    assert approx(b_vs_a, 200)
    assert approx(b_vs_c, 400)


# ---------------------------------------------------------------------------
# TC21-24 — request-level rejections
# ---------------------------------------------------------------------------

def test_tc21_duplicate_scenario_id():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("A")])
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert result["scenarios"] == []
    assert any(w["code"] == "DUPLICATE_SCENARIO_ID" for w in result["warnings"])


def test_tc22_missing_baseline_scenario_id():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B")], baseline_scenario_id=None)
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "MISSING_BASELINE_SCENARIO_ID" for w in result["warnings"])


def test_tc23_baseline_scenario_id_not_found():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B")], baseline_scenario_id="Z")
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "BASELINE_SCENARIO_ID_NOT_FOUND" for w in result["warnings"])


def test_tc24_scenario_count_one():
    base = make_base_input()
    req = make_request(base, [scenario("A")], baseline_scenario_id="A")
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "SCENARIO_COUNT_BELOW_MINIMUM" for w in result["warnings"])


def test_tc25_scenario_count_five():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B"), scenario("C"), scenario("D"), scenario("E")])
    result = run_scenario_compare(req)
    assert result["status"] in ("OK", "INCOMPLETE", "ERROR")
    assert len(result["scenarios"]) == 5


# ---------------------------------------------------------------------------
# TC26-30 — id-related request-level rejections
# ---------------------------------------------------------------------------

def test_tc26_duplicate_component_id_in_base():
    base = make_base_input()
    base["product"]["price_components"].append(dict(base["product"]["price_components"][0]))
    req = make_request(base, [scenario("A"), scenario("B")])
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "DUPLICATE_COMPONENT_ID_IN_BASE_INPUT" for w in result["warnings"])


def test_tc27_duplicate_item_id_in_base():
    base = make_base_input()
    base["costs"]["items"].append(dict(base["costs"]["items"][0]))
    req = make_request(base, [scenario("A"), scenario("B")])
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "DUPLICATE_ITEM_ID_IN_BASE_INPUT" for w in result["warnings"])


def test_tc28_unknown_component_id_override():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "addon", "actual_price": 1}]})])
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "UNKNOWN_OVERRIDE_COMPONENT_ID" for w in result["warnings"])


def test_tc29_unknown_item_id_override():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"cost_items": [{"item_id": "shipping", "amount": 1}]})])
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "UNKNOWN_OVERRIDE_ITEM_ID" for w in result["warnings"])


def test_tc30_duplicate_override_target():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [
        {"component_id": "main", "actual_price": 1100},
        {"component_id": "main", "discount_rate": 0.1},
    ]})])
    result = run_scenario_compare(req)
    assert result["status"] == "ERROR"
    assert any(w["code"] == "DUPLICATE_OVERRIDE_TARGET" for w in result["warnings"])


# ---------------------------------------------------------------------------
# TC31/32 — omitted vs explicit null
# ---------------------------------------------------------------------------

def test_tc31_omitted_field_inherits_base():
    base = make_base_input(price_includes_vat=False)
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]})])
    result = run_scenario_compare(req)
    b = result["scenarios"][1]
    # price_includes_vat was never overridden -> stays False -> N == actual_price directly
    comp = b["summary"]["per_component"]["main"]
    assert approx(comp["mode_a"]["actual_price_ex_vat"]["value"], 1200)


def test_tc32_explicit_null_creates_unknown():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": None}]})])
    result = run_scenario_compare(req)
    b = result["scenarios"][1]
    comp = b["summary"]["per_component"]["main"]
    assert comp["mode_a"]["actual_price_ex_vat"]["status"] == "UNKNOWN"
    assert comp["mode_a"]["contribution_margin"]["status"] == "UNKNOWN"
    assert comp["bep"]["contribution_margin_per_unit"]["status"] == "UNKNOWN"
    assert b["scenario_status"] == "INCOMPLETE"


# ---------------------------------------------------------------------------
# TC33/35/36 — baseline self-delta status semantics
# ---------------------------------------------------------------------------

def test_tc33_baseline_self_delta_numeric_ok():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]})])
    result = run_scenario_compare(req)
    a = result["scenarios"][0]
    d = a["deltas"]["per_component"]["main"]
    for key in ("net_sales_ex_vat_delta", "contribution_margin_delta", "contribution_margin_rate_delta", "break_even_quantity_delta"):
        assert d[key] == {"value": 0, "status": "OK"}


def test_tc35_baseline_self_delta_unknown():
    base = make_base_input()
    req = make_request(base, [
        scenario("A", overrides={"components": [{"component_id": "main", "price_includes_vat": True}], "tax": {"vat_rate": None}}),
        scenario("B"),
    ], baseline_scenario_id="A")
    result = run_scenario_compare(req)
    a = result["scenarios"][0]
    assert a["scenario_status"] == "INCOMPLETE"
    d = a["deltas"]["per_component"]["main"]
    assert d["contribution_margin_delta"] == {"value": None, "status": "UNKNOWN"}


def test_tc36_baseline_self_delta_not_applicable():
    base = make_base_input()
    req = make_request(base, [
        scenario("A", overrides={"components": [{"component_id": "main", "actual_price": 500}]}),
        scenario("B"),
    ], baseline_scenario_id="A")
    result = run_scenario_compare(req)
    a = result["scenarios"][0]
    d = a["deltas"]["per_component"]["main"]
    assert d["break_even_quantity_delta"] == {"value": None, "status": "NOT_APPLICABLE"}
    # contribution_margin itself is a numeric 0 -> that delta is 0/OK, unaffected by BEP's NOT_APPLICABLE
    assert d["contribution_margin_delta"] == {"value": 0, "status": "OK"}


# ---------------------------------------------------------------------------
# TC37 — invalid baseline at STEP 3
# ---------------------------------------------------------------------------

def test_tc37_invalid_baseline_step3_siblings_preserved():
    base = make_base_input()
    req = make_request(base, [
        scenario("W", overrides={"cost_items": [{"item_id": "direct", "rate": 1.5}]}),
        scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]}),
        scenario("D", overrides={"cost_items": [{"item_id": "direct", "amount": 300}]}),
    ], baseline_scenario_id="W")
    result = run_scenario_compare(req)
    w = result["scenarios"][0]
    b = result["scenarios"][1]
    d = result["scenarios"][2]

    assert w["scenario_status"] == "ERROR"
    assert "results" not in w
    assert "summary" not in w
    assert "deltas" not in w  # STEP3-invalid scenario never gets a fake delta on itself either

    # siblings still ran fully and have correct absolute numbers
    assert approx(b["summary"]["per_component"]["main"]["mode_a"]["contribution_margin"]["value"], 700)
    assert approx(d["summary"]["per_component"]["main"]["mode_a"]["contribution_margin"]["value"], 600)

    for entry in (b, d):
        delta = entry["deltas"]["per_component"]["main"]
        for key in delta:
            assert delta[key] == {"value": None, "status": "ERROR"}
        # BASELINE_SCENARIO_INVALID_FOR_DELTA must NOT be duplicated into sibling warnings
        assert not any(w2["code"] == "BASELINE_SCENARIO_INVALID_FOR_DELTA" for w2 in entry["warnings"])

    assert result["status"] == "ERROR"

    # the warning is recorded exactly once, at the top level
    top_level_codes = [w2["code"] for w2 in result["warnings"]]
    assert top_level_codes.count("BASELINE_SCENARIO_INVALID_FOR_DELTA") == 1
    baseline_warning = result["warnings"][0]
    assert baseline_warning["origin_module"] == "scenario_compare"


def test_baseline_invalid_warning_not_duplicated_across_three_siblings():
    """Same as TC37 but with 3 valid siblings — the count must stay exactly 1 regardless of how
    many scenarios depend on the broken baseline."""
    base = make_base_input()
    req = make_request(base, [
        scenario("W", overrides={"cost_items": [{"item_id": "direct", "rate": 1.5}]}),
        scenario("B1", overrides={"components": [{"component_id": "main", "actual_price": 1100}]}),
        scenario("B2", overrides={"components": [{"component_id": "main", "actual_price": 1200}]}),
        scenario("B3", overrides={"cost_items": [{"item_id": "direct", "amount": 300}]}),
    ], baseline_scenario_id="W")
    result = run_scenario_compare(req)

    top_level_codes = [w["code"] for w in result["warnings"]]
    assert top_level_codes.count("BASELINE_SCENARIO_INVALID_FOR_DELTA") == 1

    for sid in ("B1", "B2", "B3"):
        entry = next(e for e in result["scenarios"] if e["scenario_id"] == sid)
        assert not any(w["code"] == "BASELINE_SCENARIO_INVALID_FOR_DELTA" for w in entry["warnings"])
        for key, d in entry["deltas"]["per_component"]["main"].items():
            assert d == {"value": None, "status": "ERROR"}, key
        # absolute results still present and correct
        assert entry["summary"]["per_component"]["main"]["mode_a"]["status"] == "OK"


def test_step3_invalid_non_baseline_scenario_has_no_fake_delta():
    """A non-baseline scenario that itself fails STEP 3 gets no results/summary/deltas at all —
    contrast with a VALID sibling of an invalid baseline, which DOES get an ERROR delta (SPEC.md
    section 14a's distinction: 'no data to compute from' vs 'data present, but the comparison
    target is broken')."""
    base = make_base_input()
    req = make_request(base, [
        scenario("A"),
        scenario("X", overrides={"cost_items": [{"item_id": "direct", "rate": 1.5}]}),
    ], baseline_scenario_id="A")
    result = run_scenario_compare(req)
    x = next(e for e in result["scenarios"] if e["scenario_id"] == "X")
    assert x["scenario_status"] == "ERROR"
    assert "results" not in x
    assert "summary" not in x
    assert "deltas" not in x
    assert result["warnings"] == []  # baseline itself was fine; this is a scenario-local failure


# ---------------------------------------------------------------------------
# Cross-cutting tests
# ---------------------------------------------------------------------------

def test_base_input_not_mutated():
    base = make_base_input()
    base_copy = copy.deepcopy(base)
    req = make_request(base, [scenario("A"), scenario("B", overrides={
        "components": [{"component_id": "main", "actual_price": 1200}],
        "cost_items": [{"item_id": "direct", "amount": 999}],
    })])
    run_scenario_compare(req)
    assert base == base_copy


def test_warning_origin_module_preserved_for_mode_warnings():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={
        "components": [{"component_id": "main", "price_includes_vat": True}],
        "tax": {"vat_rate": None},
    })])
    result = run_scenario_compare(req)
    b = result["scenarios"][1]
    origins = {w["origin_module"] for w in b["warnings"]}
    assert origins <= {"mode_a", "mode_b", "mode_c", "bep", "scenario_compare"}
    for w in b["warnings"]:
        if w["origin_module"] == "mode_a":
            assert w["metric_path"].startswith("mode_a.")


def test_mode_outputs_equal_direct_engine_invocation():
    from core.engine.modes.mode_a import run_mode_a
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B")])
    result = run_scenario_compare(req)
    direct = run_mode_a(base)
    assert result["scenarios"][0]["results"]["mode_a"] == direct


def test_component_id_mapping_order_independent():
    base = make_base_input(extra_components=[{
        "component_id": "addon", "type": "one_time", "actual_price": 500,
        "currency": "KRW", "price_includes_vat": False,
    }])
    reordered = copy.deepcopy(base)
    reordered["product"]["price_components"].reverse()

    req1 = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "addon", "actual_price": 600}]})])
    req2 = make_request(reordered, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "addon", "actual_price": 600}]})])
    r1 = run_scenario_compare(req1)
    r2 = run_scenario_compare(req2)
    # both should still target the "addon" component correctly regardless of array order
    b1 = r1["scenarios"][1]["results"]["mode_a"]["per_component"]["addon"] if r1["scenarios"][1].get("results") else None
    b2 = r2["scenarios"][1]["results"]["mode_a"]["per_component"]["addon"] if r2["scenarios"][1].get("results") else None
    assert b1 is not None and b2 is not None
    assert b1["actual_price_ex_vat"]["value"] == b2["actual_price_ex_vat"]["value"] == 600


def test_no_new_calculation_formula_contribution_margin_matches_mode_a():
    """Scenario Compare's summary CM must be byte-identical to MODE A's own output — never a
    recomputation."""
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1234}]})])
    result = run_scenario_compare(req)
    b = result["scenarios"][1]
    assert b["summary"]["per_component"]["main"]["mode_a"]["contribution_margin"] == b["results"]["mode_a"]["per_component"]["main"]["contribution_margin"]


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_request_schema_validates():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]})])
    assert validate_scenario_compare_request(req) == []


def test_result_schema_validates_for_ok_and_error_cases():
    base = make_base_input()
    req_ok = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]})])
    result_ok = run_scenario_compare(req_ok)
    assert validate_scenario_compare_result(result_ok) == []

    req_bad = make_request(base, [scenario("A"), scenario("A")])
    result_bad = run_scenario_compare(req_bad)
    assert validate_scenario_compare_result(result_bad) == []

    req_step3 = make_request(base, [
        scenario("W", overrides={"cost_items": [{"item_id": "direct", "rate": 1.5}]}),
        scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]}),
    ], baseline_scenario_id="W")
    result_step3 = run_scenario_compare(req_step3)
    assert validate_scenario_compare_result(result_step3) == []


def test_invalid_request_field_outside_allowlist_rejected_by_schema():
    base = make_base_input()
    req = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "cost_category": "direct"}]})])
    errors = validate_scenario_compare_request(req)
    assert errors  # "cost_category" is not an allowed component-override field


# ---------------------------------------------------------------------------
# STEP 1 request-level ERROR result — canonical shape + schema validity, per failure type
# ---------------------------------------------------------------------------

def _step1_failing_requests():
    base = make_base_input()

    base_dup_component = make_base_input()
    base_dup_component["product"]["price_components"].append(dict(base_dup_component["product"]["price_components"][0]))

    base_dup_item = make_base_input()
    base_dup_item["costs"]["items"].append(dict(base_dup_item["costs"]["items"][0]))

    return {
        "scenario_count_below_minimum": make_request(base, [scenario("A")], baseline_scenario_id="A"),
        "duplicate_scenario_id": make_request(base, [scenario("A"), scenario("A")]),
        "missing_baseline_scenario_id": make_request(base, [scenario("A"), scenario("B")], baseline_scenario_id=None),
        "baseline_scenario_id_not_found": make_request(base, [scenario("A"), scenario("B")], baseline_scenario_id="Z"),
        "duplicate_component_id_in_base_input": make_request(base_dup_component, [scenario("A"), scenario("B")]),
        "duplicate_item_id_in_base_input": make_request(base_dup_item, [scenario("A"), scenario("B")]),
        "unknown_override_component_id": make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "addon", "actual_price": 1}]})]),
        "unknown_override_item_id": make_request(base, [scenario("A"), scenario("B", overrides={"cost_items": [{"item_id": "shipping", "amount": 1}]})]),
        "duplicate_override_target": make_request(base, [scenario("A"), scenario("B", overrides={"components": [
            {"component_id": "main", "actual_price": 1100}, {"component_id": "main", "discount_rate": 0.1},
        ]})]),
    }


def test_step1_failures_produce_canonical_error_result_and_valid_schema():
    import core.engine.scenario_compare as sc_module

    call_counter = {"mode_a": 0, "mode_b": 0, "mode_c": 0, "bep": 0}
    originals = {
        "run_mode_a": sc_module.run_mode_a, "run_mode_b": sc_module.run_mode_b,
        "run_mode_c": sc_module.run_mode_c, "run_bep": sc_module.run_bep,
    }

    def _counting(name, fn):
        def wrapper(*args, **kwargs):
            call_counter[name] += 1
            return fn(*args, **kwargs)
        return wrapper

    sc_module.run_mode_a = _counting("mode_a", originals["run_mode_a"])
    sc_module.run_mode_b = _counting("mode_b", originals["run_mode_b"])
    sc_module.run_mode_c = _counting("mode_c", originals["run_mode_c"])
    sc_module.run_bep = _counting("bep", originals["run_bep"])
    try:
        for label, req in _step1_failing_requests().items():
            result = run_scenario_compare(req)
            assert result["status"] == "ERROR", label
            assert result["scenarios"] == [], label
            assert len(result["warnings"]) >= 1, label
            schema_errors = validate_scenario_compare_result(result)
            assert schema_errors == [], (label, schema_errors)
    finally:
        sc_module.run_mode_a = originals["run_mode_a"]
        sc_module.run_mode_b = originals["run_mode_b"]
        sc_module.run_mode_c = originals["run_mode_c"]
        sc_module.run_bep = originals["run_bep"]

    assert call_counter == {"mode_a": 0, "mode_b": 0, "mode_c": 0, "bep": 0}


def test_step1_failures_produce_expected_warning_codes():
    expected_codes = {
        "scenario_count_below_minimum": "SCENARIO_COUNT_BELOW_MINIMUM",
        "duplicate_scenario_id": "DUPLICATE_SCENARIO_ID",
        "missing_baseline_scenario_id": "MISSING_BASELINE_SCENARIO_ID",
        "baseline_scenario_id_not_found": "BASELINE_SCENARIO_ID_NOT_FOUND",
        "duplicate_component_id_in_base_input": "DUPLICATE_COMPONENT_ID_IN_BASE_INPUT",
        "duplicate_item_id_in_base_input": "DUPLICATE_ITEM_ID_IN_BASE_INPUT",
        "unknown_override_component_id": "UNKNOWN_OVERRIDE_COMPONENT_ID",
        "unknown_override_item_id": "UNKNOWN_OVERRIDE_ITEM_ID",
        "duplicate_override_target": "DUPLICATE_OVERRIDE_TARGET",
    }
    requests = _step1_failing_requests()
    for label, code in expected_codes.items():
        result = run_scenario_compare(requests[label])
        codes = [w["code"] for w in result["warnings"]]
        assert code in codes, (label, codes)
        assert all(w["origin_module"] == "scenario_compare" for w in result["warnings"]), label


# ---------------------------------------------------------------------------
# Result schema strictness across all three top-level shapes
# ---------------------------------------------------------------------------

def test_result_schema_strict_across_all_three_shapes():
    base = make_base_input()

    # A. normal scenario result
    req_ok = make_request(base, [scenario("A"), scenario("B", overrides={"components": [{"component_id": "main", "actual_price": 1200}]})])
    result_ok = run_scenario_compare(req_ok)
    assert validate_scenario_compare_result(result_ok) == []
    assert "results" in result_ok["scenarios"][0]

    # B. partial result: one STEP3-invalid non-baseline scenario alongside a valid one
    req_partial = make_request(base, [
        scenario("A"),
        scenario("X", overrides={"cost_items": [{"item_id": "direct", "rate": 1.5}]}),
    ])
    result_partial = run_scenario_compare(req_partial)
    assert validate_scenario_compare_result(result_partial) == []

    # C. STEP1 request-level ERROR result: status=ERROR, scenarios=[]
    req_error = make_request(base, [scenario("A"), scenario("A")])
    result_error = run_scenario_compare(req_error)
    assert result_error["status"] == "ERROR"
    assert result_error["scenarios"] == []
    assert validate_scenario_compare_result(result_error) == []
