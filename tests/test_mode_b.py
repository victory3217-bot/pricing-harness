# -*- coding: utf-8 -*-
"""
Unit tests for MODE B (core/engine/modes/mode_b.py).

Every numeric expectation here is hand-checked against
docs/features/mode_b_target_price/SPEC.md v0.2 (TC1-TC12) — this file's test numbers are
labeled with which SPEC.md TC they match where applicable. Fixtures are intentionally minimal
and independent from core/schemas/examples/ (which exist to demonstrate the schema, not pin
exact engine outputs).
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.modes.mode_b import run_mode_b  # noqa: E402
from core.engine.result_builder import build_analysis_result  # noqa: E402
from core.engine.validation.validate_client_input import assert_valid_client_input  # noqa: E402

APPROX = 1e-4


def approx(a, b, tol=APPROX):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def make_input(*, price_includes_vat, direct_cost, vat_rate, target_cm_rate,
                net_sales_fee_rate=None, gross_payment_fee_rate=None,
                extra_cost_items=None, discount_rate=None, direct_cost_is_null=False):
    """Builds a minimal single-component Client Input for MODE B.

    direct_cost -> C (product_service_direct_cost, amount-based).
    net_sales_fee_rate -> b (one rate_of_net_sales variable item), omitted if None.
    gross_payment_fee_rate -> a (one rate_of_gross_payment variable item), omitted if None.
    """
    items = []
    if direct_cost_is_null:
        items.append({
            "item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
            "amount": None, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main",
        })
    else:
        items.append({
            "item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
            "amount": direct_cost, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main",
        })
    if net_sales_fee_rate is not None:
        items.append({
            "item_id": "channel_fee", "label": "채널수수료", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": net_sales_fee_rate, "currency": None, "basis": "rate_of_net_sales",
            "applies_to_component": "main",
        })
    if gross_payment_fee_rate is not None:
        items.append({
            "item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": gross_payment_fee_rate, "currency": None, "basis": "rate_of_gross_payment",
            "applies_to_component": "main",
        })
    if extra_cost_items:
        items.extend(extra_cost_items)

    component = {
        "component_id": "main",
        "type": "one_time",
        "actual_price": 1,  # MODE B solves for price; actual_price is unused input noise here
        "currency": "KRW",
        "price_includes_vat": price_includes_vat,
    }
    if discount_rate is not None or discount_rate is None:
        component["discount_rate"] = discount_rate

    return {
        "schema_version": "1.1",
        "client_id": "unit_test_co",
        "case_id": "unit_test_case_mode_b",
        "product": {
            "name": "MODE B 테스트 상품",
            "pricing_model": "one_time",
            "price_components": [component],
        },
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": target_cm_rate},
        "meta": {"entered_by": "unit_test", "entered_at": "2026-09-11", "notes": ""},
    }


def m(result, name):
    return result["per_component"]["main"][name]


# ---------------------------------------------------------------------------
# 1. rate 비용 없는 단순 케이스 (TC1: a=0, b=0)
# ---------------------------------------------------------------------------
def test_1_no_rate_cost_at_all():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.4)
    assert_valid_client_input(ci)
    result = run_mode_b(ci)

    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert approx(n["value"], 16666.67)

    g = m(result, "required_gross_payment_incl_vat")
    assert g["status"] == "OK"
    assert approx(g["value"], 18333.33)

    cm = m(result, "expected_contribution_margin_rate")
    assert cm["status"] == "OK"
    assert approx(cm["value"], 0.4)


def test_1b_no_rate_cost_v_unknown_still_leaves_n_ok():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=None, target_cm_rate=0.4)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert approx(n["value"], 16666.67)
    g = m(result, "required_gross_payment_incl_vat")
    assert g["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 2. net-sales fee only (TC2)
# ---------------------------------------------------------------------------
def test_2_net_sales_fee_only():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
                     net_sales_fee_rate=0.1)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert approx(n["value"], 16666.67)
    g = m(result, "required_gross_payment_incl_vat")
    assert approx(g["value"], 18333.33)


# ---------------------------------------------------------------------------
# 3. gross-payment fee only, v known, VAT-exclusive display (TC3)
# ---------------------------------------------------------------------------
def test_3_gross_payment_fee_only_vat_exclusive_display():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
                     gross_payment_fee_rate=0.05)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert approx(n["value"], 15503.88, tol=1e-3)
    g = m(result, "required_gross_payment_incl_vat")
    assert approx(g["value"], 17054.27, tol=1e-3)
    s = m(result, "required_selling_price")
    assert s["status"] == "OK"
    assert approx(s["value"], n["value"])  # display basis is N since price_includes_vat=false


# ---------------------------------------------------------------------------
# 4. VAT-inclusive display, both fee types (TC4)
# ---------------------------------------------------------------------------
def test_4_vat_inclusive_display_both_fee_types():
    ci = make_input(price_includes_vat=True, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
                     net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert approx(n["value"], 17636.68, tol=1e-3)
    g = m(result, "required_gross_payment_incl_vat")
    assert approx(g["value"], 19400.35, tol=1e-3)
    s = m(result, "required_selling_price")
    assert approx(s["value"], g["value"])  # display basis is G since price_includes_vat=true
    cmr = m(result, "expected_contribution_margin_rate")
    assert approx(cmr["value"], 0.3)


# ---------------------------------------------------------------------------
# 5. VAT-exclusive display, both fee types (TC5)
# ---------------------------------------------------------------------------
def test_5_vat_exclusive_display_both_fee_types():
    ci = make_input(price_includes_vat=False, direct_cost=8000, vat_rate=0.10, target_cm_rate=0.25,
                     net_sales_fee_rate=0.05, gross_payment_fee_rate=0.02)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert approx(n["value"], 11799.41, tol=1e-3)
    g = m(result, "required_gross_payment_incl_vat")
    assert approx(g["value"], 12979.35, tol=1e-3)
    cmr = m(result, "expected_contribution_margin_rate")
    assert approx(cmr["value"], 0.25)


# ---------------------------------------------------------------------------
# 6. VAT-exclusive display, v UNKNOWN, gross-payment fee present (TC11)
# ---------------------------------------------------------------------------
def test_6_vat_exclusive_v_unknown_gross_payment_fee_blocks_everything():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=None, target_cm_rate=0.3,
                     gross_payment_fee_rate=0.05)
    result = run_mode_b(ci)
    assert m(result, "required_net_sales_ex_vat")["status"] == "UNKNOWN"
    assert m(result, "required_gross_payment_incl_vat")["status"] == "UNKNOWN"
    assert m(result, "required_selling_price")["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 7. VAT-exclusive display, v UNKNOWN, net-sales fee only (TC12)
# ---------------------------------------------------------------------------
def test_7_vat_exclusive_v_unknown_net_sales_fee_only_n_stays_ok():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=None, target_cm_rate=0.3,
                     net_sales_fee_rate=0.1)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert approx(n["value"], 16666.67)
    g = m(result, "required_gross_payment_incl_vat")
    assert g["status"] == "UNKNOWN"
    s = m(result, "required_selling_price")
    assert s["status"] == "OK"
    assert approx(s["value"], 16666.67)
    lp = m(result, "required_list_price")
    assert lp["status"] == "UNKNOWN"  # discount_rate not provided -> null -> UNKNOWN, not silently OK


# ---------------------------------------------------------------------------
# 8. VAT-inclusive display, v UNKNOWN -> N can be OK (a=0) but selling_price (=G) is UNKNOWN
# ---------------------------------------------------------------------------
def test_8_vat_inclusive_v_unknown_blocks_selling_price_via_g():
    ci = make_input(price_includes_vat=True, direct_cost=10000, vat_rate=None, target_cm_rate=0.3,
                     net_sales_fee_rate=0.1)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"  # a=0, v not needed for N
    g = m(result, "required_gross_payment_incl_vat")
    assert g["status"] == "UNKNOWN"  # G always needs v
    s = m(result, "required_selling_price")
    assert s["status"] == "UNKNOWN"  # display basis is G since price_includes_vat=true


# ---------------------------------------------------------------------------
# 9. discount_rate = 0 -> list price equals selling price
# ---------------------------------------------------------------------------
def test_9_discount_rate_zero():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.4,
                     discount_rate=0)
    result = run_mode_b(ci)
    s = m(result, "required_selling_price")
    lp = m(result, "required_list_price")
    assert lp["status"] == "OK"
    assert approx(lp["value"], s["value"])


# ---------------------------------------------------------------------------
# 10. discount_rate normal value (TC6, on top of TC4)
# ---------------------------------------------------------------------------
def test_10_discount_rate_normal_value():
    ci = make_input(price_includes_vat=True, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
                     net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03, discount_rate=0.10)
    result = run_mode_b(ci)
    lp = m(result, "required_list_price")
    assert lp["status"] == "OK"
    assert approx(lp["value"], 21555.95, tol=1e-3)


# ---------------------------------------------------------------------------
# 11. discount_rate >= 1 -> ERROR
# ---------------------------------------------------------------------------
def test_11_discount_rate_ge_1_is_error():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.4,
                     discount_rate=1.0)
    result = run_mode_b(ci)
    lp = m(result, "required_list_price")
    assert lp["status"] == "ERROR"
    assert lp["value"] is None


# ---------------------------------------------------------------------------
# 12. target CM rate = 1 -> denominator <= 0 -> ERROR
# ---------------------------------------------------------------------------
def test_12_target_cm_rate_at_max_makes_denominator_error():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=1.0)
    result = run_mode_b(ci)
    d = m(result, "denominator")
    assert d["status"] == "ERROR"
    assert d["value"] is not None and d["value"] <= 0
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 13. denominator <= 0 with both fee types (TC7)
# ---------------------------------------------------------------------------
def test_13_denominator_le_zero_error():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.5,
                     net_sales_fee_rate=0.3, gross_payment_fee_rate=0.3)
    result = run_mode_b(ci)
    d = m(result, "denominator")
    assert d["status"] == "ERROR"
    assert approx(d["value"], -0.13, tol=1e-3)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "ERROR"
    g = m(result, "required_gross_payment_incl_vat")
    assert g["status"] == "ERROR"
    s = m(result, "required_selling_price")
    assert s["status"] == "ERROR"
    # module status: canonical 3-tier — any ERROR metric -> module ERROR (dependency_rules.md §5)
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 14. UNKNOWN cost (TC8: direct cost amount null)
# ---------------------------------------------------------------------------
def test_14_unknown_direct_cost_blocks_everything():
    ci = make_input(price_includes_vat=False, direct_cost=None, vat_rate=0.10, target_cm_rate=0.3,
                     direct_cost_is_null=True)
    result = run_mode_b(ci)
    for name in ("required_net_sales_ex_vat", "required_gross_payment_incl_vat",
                 "required_selling_price", "required_list_price"):
        assert m(result, name)["status"] == "UNKNOWN", name
    # no ERROR anywhere, at least one UNKNOWN -> module INCOMPLETE, not ERROR
    assert result["status"] == "INCOMPLETE"


# ---------------------------------------------------------------------------
# 15. explicit zero rate does not block computation (TC9)
# ---------------------------------------------------------------------------
def test_15_explicit_zero_rate_is_not_unknown():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
                     net_sales_fee_rate=0.0, gross_payment_fee_rate=0.05)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert approx(n["value"], 15503.88, tol=1e-3)  # identical to TC3 — explicit-0 channel fee adds nothing


# ---------------------------------------------------------------------------
# 16. negative discount_rate -> ERROR
# ---------------------------------------------------------------------------
def test_16_negative_discount_rate_is_error():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.4,
                     discount_rate=-0.1)
    result = run_mode_b(ci)
    lp = m(result, "required_list_price")
    assert lp["status"] == "ERROR"
    assert lp["value"] is None


# ---------------------------------------------------------------------------
# 17 (A) — shared fixed-amount cost, allocation unresolved -> C UNKNOWN, not silently 0.
# ---------------------------------------------------------------------------
def test_17_shared_fixed_amount_cost_unresolved_blocks_c_not_ignored():
    ci = make_input(
        price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.4,
        extra_cost_items=[{
            "item_id": "shared_infra", "label": "공유 인프라비", "cost_category": "product_service_direct_cost",
            "amount": 5000, "rate": None, "currency": "KRW", "basis": "per_month",
            "applies_to_component": "shared", "allocation_rule": "by_component_revenue",
        }],
    )
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "UNKNOWN"
    assert n["value"] is None
    # must NOT silently compute as if the shared cost were 0 (that would give 16666.67)
    assert not approx(n.get("value") or 0, 16666.67)

    n_warning = next(w for w in result["warnings"]
                      if w["metric_path"] == "mode_b.per_component.main.required_net_sales_ex_vat")
    assert n_warning["code"] == "UNSUPPORTED_SHARED_COST_ALLOCATION"
    assert "blended.allocation[shared_infra]" in n_warning["dependency_paths"]

    # denominator doesn't depend on C -- only required_net_sales_ex_vat (and downstream) is blocked
    assert m(result, "denominator")["status"] == "OK"


# ---------------------------------------------------------------------------
# 18 (B) — shared rate_of_net_sales fee, allocation unresolved -> b-side UNKNOWN.
# ---------------------------------------------------------------------------
def test_18_shared_net_sales_rate_unresolved_blocks_denominator():
    ci = make_input(
        price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "shared_channel_fee", "label": "공유 채널수수료", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
            "applies_to_component": "shared", "allocation_rule": "fixed_share",
        }],
    )
    result = run_mode_b(ci)
    d = m(result, "denominator")
    assert d["status"] == "UNKNOWN"
    d_warning = next(w for w in result["warnings"]
                      if w["metric_path"] == "mode_b.per_component.main.denominator")
    assert d_warning["code"] == "UNSUPPORTED_SHARED_COST_ALLOCATION"
    assert "blended.allocation[shared_channel_fee]" in d_warning["dependency_paths"]
    for name in ("required_net_sales_ex_vat", "required_gross_payment_incl_vat",
                 "required_selling_price", "expected_contribution_margin"):
        assert m(result, name)["status"] == "UNKNOWN", name


# ---------------------------------------------------------------------------
# 19 (C) — shared rate_of_gross_payment fee, allocation unresolved -> a-side UNKNOWN.
# ---------------------------------------------------------------------------
def test_19_shared_gross_payment_rate_unresolved_blocks_denominator():
    ci = make_input(
        price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "shared_pg_fee", "label": "공유 PG수수료", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": 0.05, "currency": None, "basis": "rate_of_gross_payment",
            "applies_to_component": "shared",  # allocation_rule missing entirely
        }],
    )
    result = run_mode_b(ci)
    d = m(result, "denominator")
    assert d["status"] == "UNKNOWN"
    d_warning = next(w for w in result["warnings"]
                      if w["metric_path"] == "mode_b.per_component.main.denominator")
    assert d_warning["code"] == "UNSUPPORTED_SHARED_COST_ALLOCATION"
    assert "costs.items[shared_pg_fee].allocation_rule" in d_warning["dependency_paths"]


# ---------------------------------------------------------------------------
# 20 (D) — no shared cost at all -> no regression vs. TC3's plain result.
# ---------------------------------------------------------------------------
def test_20_no_shared_cost_no_regression():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
                     gross_payment_fee_rate=0.05)
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "OK"
    assert approx(n["value"], 15503.88, tol=1e-3)


# ---------------------------------------------------------------------------
# 21 (E) — applies_to_component="shared" + allocation_rule="direct" is a semantically
# contradictory configuration ("shared" = not attributed to one component; "direct" = already
# attributed to one). MODE B must refuse to guess and report ERROR, not quietly apply the cost
# as if it were a normal per-component item.
# ---------------------------------------------------------------------------
def test_21_shared_plus_direct_allocation_is_invalid_configuration():
    ci = make_input(
        price_includes_vat=False, direct_cost=0, vat_rate=0.10, target_cm_rate=0.4,
        extra_cost_items=[{
            "item_id": "shared_direct", "label": "모순 설정: shared + direct", "cost_category": "product_service_direct_cost",
            "amount": 10000, "rate": None, "currency": "KRW", "basis": "per_unit",
            "applies_to_component": "shared", "allocation_rule": "direct",
        }],
    )
    result = run_mode_b(ci)
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "ERROR"
    assert n["value"] is None

    n_warning = next(w for w in result["warnings"]
                      if w["metric_path"] == "mode_b.per_component.main.required_net_sales_ex_vat")
    assert n_warning["code"] == "INVALID_ALLOCATION_CONFIGURATION"
    assert "costs.items[shared_direct].allocation_rule" in n_warning["dependency_paths"]

    # downstream metrics must propagate ERROR too, not silently resolve
    for name in ("required_gross_payment_incl_vat", "required_selling_price",
                 "expected_contribution_margin", "expected_contribution_margin_rate"):
        assert m(result, name)["status"] == "ERROR", name
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 21b — same contradiction on a rate_of_net_sales fee -> denominator itself is ERROR
# (INVALID_ALLOCATION_CONFIGURATION), distinct from the "denominator <= 0" ERROR case.
# ---------------------------------------------------------------------------
def test_21b_shared_plus_direct_on_net_sales_rate_makes_denominator_invalid():
    ci = make_input(
        price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3,
        extra_cost_items=[{
            "item_id": "shared_channel_direct", "label": "모순 설정: shared + direct 수수료",
            "cost_category": "variable_selling_delivery",
            "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
            "applies_to_component": "shared", "allocation_rule": "direct",
        }],
    )
    result = run_mode_b(ci)
    d = m(result, "denominator")
    assert d["status"] == "ERROR"
    d_warning = next(w for w in result["warnings"]
                      if w["metric_path"] == "mode_b.per_component.main.denominator")
    assert d_warning["code"] == "INVALID_ALLOCATION_CONFIGURATION"
    assert "costs.items[shared_channel_direct].allocation_rule" in d_warning["dependency_paths"]
    n = m(result, "required_net_sales_ex_vat")
    assert n["status"] == "ERROR"
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 22 (E) — the checked-in hybrid example has three real shared items
# (pg_fee/channel_fee: by_component_revenue; maintenance_visit: fixed_share). With a target CM
# rate set, MODE B must NOT compute a plausible-looking (but too-low) target price for either
# component by ignoring them -- both must come back UNKNOWN, and the shared-allocation
# dependency must not leak into meta.missing_input_paths (it isn't a missing user input).
# ---------------------------------------------------------------------------
def test_22_hybrid_example_shared_costs_do_not_produce_wrong_target_price():
    ci = json.loads((ROOT / "core/schemas/examples/valid/03_hybrid_hw_saas.json").read_text(encoding="utf-8"))
    ci = copy.deepcopy(ci)
    ci["targets"]["target_contribution_margin_rate"] = 0.30
    assert_valid_client_input(ci)

    result = run_mode_b(ci)
    for cid in ("hardware", "saas_subscription"):
        n = result["per_component"][cid]["required_net_sales_ex_vat"]
        assert n["status"] == "UNKNOWN"
        assert n["value"] is None

    codes = {w["code"] for w in result["warnings"]}
    assert "UNSUPPORTED_SHARED_COST_ALLOCATION" in codes

    analysis_result = build_analysis_result(ci, client_input_ref="test")
    missing = analysis_result["meta"]["missing_input_paths"]
    assert not any(p.startswith("blended.allocation[") for p in missing)


# ---------------------------------------------------------------------------
# 23-25 — canonical 3-tier module status (dependency_rules.md section 5): ERROR takes priority
# over UNKNOWN, which takes priority over OK. These three pin the tiering explicitly, on top of
# the per-scenario module-status assertions added to tests 13/21/21b above.
# ---------------------------------------------------------------------------
def test_23_module_status_ok_when_every_metric_ok():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.4,
                     discount_rate=0)
    result = run_mode_b(ci)
    assert all(v["status"] == "OK" for v in result["per_component"]["main"].values())
    assert result["status"] == "OK"


def test_24_module_status_incomplete_when_unknown_present_and_no_error():
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.4)
    result = run_mode_b(ci)
    statuses = {v["status"] for v in result["per_component"]["main"].values()}
    assert "ERROR" not in statuses
    assert "UNKNOWN" in statuses
    assert result["status"] == "INCOMPLETE"


def test_25_module_status_error_outranks_unknown_across_components():
    # Within a single component, denominator=ERROR cascades to every downstream metric (no
    # independent UNKNOWN survives on the same chain) -- so to see ERROR and UNKNOWN coexist in
    # one module result, use two components: one hits denominator<=0 (ERROR throughout), the
    # other is otherwise complete except a blank discount_rate (UNKNOWN only on list price).
    # aggregate_module_status pools metrics across all components -- ERROR must still win.
    ci = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.5,
                     net_sales_fee_rate=0.3, gross_payment_fee_rate=0.3)
    err_component = ci["product"]["price_components"][0]
    err_items = ci["costs"]["items"]

    ci_ok = make_input(price_includes_vat=False, direct_cost=10000, vat_rate=0.10, target_cm_rate=0.3)
    unk_component = dict(ci_ok["product"]["price_components"][0], component_id="unk")
    unk_items = [dict(item, applies_to_component="unk", item_id=f"unk_{item['item_id']}")
                 for item in ci_ok["costs"]["items"]]

    ci["product"]["price_components"] = [dict(err_component, component_id="err"), unk_component]
    ci["costs"]["items"] = (
        [dict(item, applies_to_component="err", item_id=f"err_{item['item_id']}") for item in err_items]
        + unk_items
    )
    assert_valid_client_input(ci)
    result = run_mode_b(ci)

    err_statuses = {v["status"] for v in result["per_component"]["err"].values()}
    unk_statuses = {v["status"] for v in result["per_component"]["unk"].values()}
    assert "ERROR" in err_statuses
    assert "ERROR" not in unk_statuses
    assert "UNKNOWN" in unk_statuses  # required_list_price only (discount_rate not provided)
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# 26-29 — module status must pool metrics across ALL components, not just the last one
# iterated in run_mode_b's loop, and the result must not depend on component list order.
# ---------------------------------------------------------------------------
def _two_component_ci_b(components_and_items, order, target_cm_rate=0.3):
    price_components = [components_and_items[cid][0] for cid in order]
    items = [item for cid in order for item in components_and_items[cid][1]]
    return {
        "schema_version": "1.1",
        "client_id": "unit_test_co",
        "case_id": "unit_test_case_mode_b_multi",
        "product": {"name": "멀티 컴포넌트 MODE B 테스트", "pricing_model": "hybrid", "price_components": price_components},
        "tax": {"vat_rate": 0.10},
        "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": target_cm_rate},
        "meta": {},
    }


def _error_and_ok_components_b():
    # "err": denominator <= 0 (t=0.5, b=0.3, a=0.3, v=0.10 -> D=-0.13, matches TC7)
    err_component = {"component_id": "err", "type": "one_time", "actual_price": 1,
                      "currency": "KRW", "price_includes_vat": False, "discount_rate": None}
    err_items = [
        {"item_id": "err_direct", "label": "d", "cost_category": "product_service_direct_cost",
         "amount": 10000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "err"},
        {"item_id": "err_b", "label": "b", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": 0.3, "currency": None, "basis": "rate_of_net_sales", "applies_to_component": "err"},
        {"item_id": "err_a", "label": "a", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": 0.3, "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "err"},
    ]
    # "ok": simple, fully resolvable (TC1-style, but t comes from the shared global target=0.3)
    ok_component = {"component_id": "ok", "type": "one_time", "actual_price": 1,
                     "currency": "KRW", "price_includes_vat": False, "discount_rate": 0}
    ok_items = [
        {"item_id": "ok_direct", "label": "d", "cost_category": "product_service_direct_cost",
         "amount": 10000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "ok"},
    ]
    return {"err": (err_component, err_items), "ok": (ok_component, ok_items)}


def _unknown_and_ok_components_b():
    # "unk": discount_rate not provided -> only required_list_price is UNKNOWN, nothing ERROR
    unk_component = {"component_id": "unk", "type": "one_time", "actual_price": 1,
                      "currency": "KRW", "price_includes_vat": False, "discount_rate": None}
    unk_items = [
        {"item_id": "unk_direct", "label": "d", "cost_category": "product_service_direct_cost",
         "amount": 10000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "unk"},
    ]
    ok_component = {"component_id": "ok", "type": "one_time", "actual_price": 1,
                     "currency": "KRW", "price_includes_vat": False, "discount_rate": 0}
    ok_items = [
        {"item_id": "ok_direct", "label": "d", "cost_category": "product_service_direct_cost",
         "amount": 10000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "ok"},
    ]
    return {"unk": (unk_component, unk_items), "ok": (ok_component, ok_items)}


def test_26_module_status_error_pooled_across_all_components_err_first():
    ci = _two_component_ci_b(_error_and_ok_components_b(), order=["err", "ok"], target_cm_rate=0.5)
    # ok component uses the same global t=0.5 -- recompute its expectation: D=1-0.5=0.5, fine (OK)
    result = run_mode_b(ci)
    assert result["per_component"]["err"]["denominator"]["status"] == "ERROR"
    assert result["per_component"]["ok"]["denominator"]["status"] == "OK"
    assert result["status"] == "ERROR"


def test_27_module_status_error_pooled_across_all_components_ok_first():
    # same scenario, component order reversed -> result must be identical (order-independent).
    # This is the case that would silently pass if run_mode_b only looked at the LAST
    # component's metrics instead of pooling every component (a "last-component dependency" bug).
    ci = _two_component_ci_b(_error_and_ok_components_b(), order=["ok", "err"], target_cm_rate=0.5)
    result = run_mode_b(ci)
    assert result["status"] == "ERROR"


def test_28_module_status_incomplete_pooled_across_all_components_unk_first():
    ci = _two_component_ci_b(_unknown_and_ok_components_b(), order=["unk", "ok"], target_cm_rate=0.3)
    result = run_mode_b(ci)
    assert result["per_component"]["unk"]["required_list_price"]["status"] == "UNKNOWN"
    assert result["per_component"]["ok"]["required_list_price"]["status"] == "OK"
    all_statuses = {v["status"] for c in result["per_component"].values() for v in c.values()}
    assert "ERROR" not in all_statuses
    assert "UNKNOWN" in all_statuses
    assert result["status"] == "INCOMPLETE"


def test_29_module_status_incomplete_pooled_across_all_components_ok_first():
    ci = _two_component_ci_b(_unknown_and_ok_components_b(), order=["ok", "unk"], target_cm_rate=0.3)
    result = run_mode_b(ci)
    assert result["status"] == "INCOMPLETE"


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
