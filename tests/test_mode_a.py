# -*- coding: utf-8 -*-
"""
Unit tests for MODE A (core/engine/modes/mode_a.py).

Each test defines its own minimal, hand-computed Client Input fixture so expected
values can be verified by hand rather than trusted blindly. Fixtures here are
intentionally small and distinct from core/schemas/examples/ (which exist to
demonstrate the schema, not to pin exact engine outputs).
"""
import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine.modes.mode_a import run_mode_a  # noqa: E402
from core.engine.validation.validate_client_input import assert_valid_client_input  # noqa: E402

APPROX = 1e-6


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def base_component(**overrides):
    c = {
        "component_id": "main",
        "type": "one_time",
        "actual_price": 35000,
        "currency": "KRW",
        "price_includes_vat": True,
    }
    c.update(overrides)
    return c


def base_input(**overrides):
    ci = {
        "schema_version": "1.1",
        "client_id": "unit_test_co",
        "case_id": "unit_test_case",
        "product": {
            "name": "테스트 상품",
            "pricing_model": "one_time",
            "price_components": [base_component()],
        },
        "tax": {"vat_rate": 0.10},
        "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
        "costs": {
            "items": [
                {"item_id": "material", "label": "자재원가", "cost_category": "product_service_direct_cost",
                 "amount": 12000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
                {"item_id": "packaging", "label": "포장비", "cost_category": "product_service_direct_cost",
                 "amount": 1500, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
                {"item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
                 "amount": None, "rate": 0.025, "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "main"},
                {"item_id": "shipping", "label": "배송비", "cost_category": "variable_selling_delivery",
                 "amount": 3000, "rate": None, "currency": "KRW", "basis": "per_order", "applies_to_component": "main"},
            ]
        },
        "targets": {"target_contribution_margin_rate": None},
        "meta": {"entered_by": "unit_test", "entered_at": "2026-09-11", "notes": ""},
    }
    ci = copy.deepcopy(ci)
    ci.update(copy.deepcopy(overrides))
    return ci


def metric(result, component_id, name):
    return result["per_component"][component_id][name]


# ---------------------------------------------------------------------------
# Test 1 — 일반 단일상품 정상 계산
# ---------------------------------------------------------------------------
def test_1_simple_product_full_calculation():
    ci = base_input()
    assert_valid_client_input(ci)
    result = run_mode_a(ci)

    assert result["status"] == "OK"
    m = result["per_component"]["main"]

    ex_vat = 35000 / 1.1
    assert m["actual_price_ex_vat"]["status"] == "OK"
    assert approx(m["actual_price_ex_vat"]["value"], ex_vat)

    assert m["direct_cost_total"]["status"] == "OK"
    assert approx(m["direct_cost_total"]["value"], 13500)

    gross_profit = ex_vat - 13500
    assert approx(m["gross_profit"]["value"], gross_profit)
    assert approx(m["gross_profit_rate"]["value"], gross_profit / ex_vat)

    variable_total = 35000 * 0.025 + 3000  # pg_fee on gross payment + shipping
    assert approx(m["variable_cost_total"]["value"], variable_total)

    cm = gross_profit - variable_total
    assert approx(m["contribution_margin"]["value"], cm)
    assert approx(m["contribution_margin_rate"]["value"], cm / ex_vat)
    assert not result["warnings"]


# ---------------------------------------------------------------------------
# Test 2 — VAT 포함가격 정상 계산 (clean round numbers)
# ---------------------------------------------------------------------------
def test_2_vat_inclusive_price():
    ci = base_input(product={
        "name": "VAT 포함가 테스트",
        "pricing_model": "one_time",
        "price_components": [base_component(actual_price=11000, price_includes_vat=True)],
    })
    ci["tax"]["vat_rate"] = 0.10
    result = run_mode_a(ci)
    m = metric(result, "main", "actual_price_ex_vat")
    assert m["status"] == "OK"
    assert approx(m["value"], 10000.0)


# ---------------------------------------------------------------------------
# Test 3 — VAT 제외가격 + vat_rate null → 정상 계산 (dependency_rules.md 규칙)
# ---------------------------------------------------------------------------
def test_3_vat_exclusive_price_with_null_rate():
    ci = base_input(product={
        "name": "VAT 제외가 테스트",
        "pricing_model": "one_time",
        "price_components": [base_component(actual_price=10000, price_includes_vat=False)],
    })
    ci["tax"]["vat_rate"] = None
    result = run_mode_a(ci)
    m = metric(result, "main", "actual_price_ex_vat")
    assert m["status"] == "OK"
    assert approx(m["value"], 10000.0)


# ---------------------------------------------------------------------------
# Test 4 — 상품 직접원가 null → Gross Profit UNKNOWN (하위로 전파)
# ---------------------------------------------------------------------------
def test_4_missing_direct_cost_makes_gross_profit_unknown():
    ci = base_input()
    ci["costs"]["items"][0]["amount"] = None  # material cost unknown
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["direct_cost_total"]["status"] == "UNKNOWN"
    assert m["gross_profit"]["status"] == "UNKNOWN"
    assert m["gross_profit_rate"]["status"] == "UNKNOWN"
    assert m["contribution_margin"]["status"] == "UNKNOWN"
    assert m["contribution_margin_rate"]["status"] == "UNKNOWN"
    # variable_cost_total does NOT depend on direct cost — must stay resolvable
    assert m["variable_cost_total"]["status"] == "OK"

    codes = {w["metric_path"]: w["code"] for w in result["warnings"]}
    assert codes["mode_a.per_component.main.direct_cost_total"] == "MISSING_DEPENDENCY"
    assert codes["mode_a.per_component.main.gross_profit"] == "DOWNSTREAM_UNKNOWN"


# ---------------------------------------------------------------------------
# Test 5 — 채널수수료 rate null → Contribution Margin UNKNOWN (Gross Profit은 OK 유지)
# ---------------------------------------------------------------------------
def test_5_missing_rate_makes_contribution_margin_unknown_but_not_gross_profit():
    ci = base_input()
    ci["costs"]["items"][2]["rate"] = None  # pg_fee rate unknown
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["gross_profit"]["status"] == "OK"  # unaffected — different dependency chain
    assert m["variable_cost_total"]["status"] == "UNKNOWN"
    assert m["contribution_margin"]["status"] == "UNKNOWN"
    assert m["contribution_margin_rate"]["status"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test 6 — 비용이 실제 숫자 0 → UNKNOWN이 아니라 정상 계산
# ---------------------------------------------------------------------------
def test_6_explicit_zero_is_not_unknown():
    ci = base_input()
    ci["costs"]["items"].append({
        "item_id": "extra_fee", "label": "추가 수수료(면제)", "cost_category": "variable_selling_delivery",
        "amount": 0, "rate": None, "currency": "KRW", "basis": "per_order", "applies_to_component": "main",
    })
    result = run_mode_a(ci)
    m = result["per_component"]["main"]
    assert m["variable_cost_total"]["status"] == "OK"
    expected = 35000 * 0.025 + 3000 + 0
    assert approx(m["variable_cost_total"]["value"], expected)


# ---------------------------------------------------------------------------
# Test 7 — ecommerce 상품 → PG / Channel Fee 정상 반영 (서로 다른 base 사용)
# ---------------------------------------------------------------------------
def test_7_ecommerce_channel_and_pg_fee_use_different_bases():
    ci = base_input(
        product={
            "name": "이커머스 테스트 상품",
            "pricing_model": "one_time",
            "price_components": [base_component(actual_price=100, price_includes_vat=True)],
        },
        costs={"items": [
            {"item_id": "material", "label": "원가", "cost_category": "product_service_direct_cost",
             "amount": 30, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "channel_fee", "label": "채널수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.10, "currency": None, "basis": "rate_of_net_sales", "applies_to_component": "main"},
            {"item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.03, "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "main"},
            {"item_id": "shipping", "label": "배송비", "cost_category": "variable_selling_delivery",
             "amount": 5, "rate": None, "currency": "KRW", "basis": "per_order", "applies_to_component": "main"},
        ]},
    )
    ci["tax"]["vat_rate"] = 0.10
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    ex_vat = 100 / 1.1
    channel_fee = ex_vat * 0.10           # rate_of_net_sales -> ex-VAT revenue
    pg_fee = 100 * 0.03                   # rate_of_gross_payment -> actual (gross) payment
    expected_variable = channel_fee + pg_fee + 5

    assert m["variable_cost_total"]["status"] == "OK"
    assert approx(m["variable_cost_total"]["value"], expected_variable)

    gross_profit = ex_vat - 30
    cm = gross_profit - expected_variable
    assert approx(m["contribution_margin"]["value"], cm)


# ---------------------------------------------------------------------------
# Test 8 — HW + SaaS → component별 계산 결과 생성
# ---------------------------------------------------------------------------
def test_8_hybrid_hw_saas_produces_independent_component_results():
    ci = {
        "schema_version": "1.1",
        "client_id": "unit_test_co",
        "case_id": "unit_test_case_hybrid",
        "product": {
            "name": "하이브리드 테스트 상품",
            "pricing_model": "hybrid",
            "price_components": [
                {"component_id": "hardware", "type": "one_time", "actual_price": 500,
                 "currency": "USD", "price_includes_vat": False},
                {"component_id": "saas_subscription", "type": "recurring_monthly", "actual_price": 50,
                 "currency": "USD", "price_includes_vat": False},
            ],
        },
        "tax": {"vat_rate": 0.10},
        "fx": {"base_currency": "USD", "reporting_currency": "USD", "rate_base_per_reporting": 1},
        "costs": {"items": [
            {"item_id": "bom", "label": "BOM", "cost_category": "product_service_direct_cost",
             "amount": 200, "rate": None, "currency": "USD", "basis": "per_unit", "applies_to_component": "hardware"},
            {"item_id": "install", "label": "설치비", "cost_category": "variable_selling_delivery",
             "amount": 30, "rate": None, "currency": "USD", "basis": "per_unit", "applies_to_component": "hardware"},
            {"item_id": "cloud", "label": "클라우드원가", "cost_category": "product_service_direct_cost",
             "amount": 5, "rate": None, "currency": "USD", "basis": "per_unit_per_month", "applies_to_component": "saas_subscription"},
        ]},
        "targets": {"target_contribution_margin_rate": None},
        "meta": {"entered_by": "unit_test", "entered_at": "2026-09-11", "notes": ""},
    }
    assert_valid_client_input(ci)
    result = run_mode_a(ci)

    assert set(result["per_component"].keys()) == {"hardware", "saas_subscription"}

    hw = result["per_component"]["hardware"]
    assert hw["actual_price_ex_vat"]["status"] == "OK"
    assert approx(hw["actual_price_ex_vat"]["value"], 500)
    assert approx(hw["direct_cost_total"]["value"], 200)
    assert approx(hw["gross_profit"]["value"], 300)
    assert approx(hw["variable_cost_total"]["value"], 30)
    assert approx(hw["contribution_margin"]["value"], 270)
    assert approx(hw["contribution_margin_rate"]["value"], 270 / 500)

    saas = result["per_component"]["saas_subscription"]
    assert approx(saas["actual_price_ex_vat"]["value"], 50)
    assert approx(saas["direct_cost_total"]["value"], 5)
    assert approx(saas["gross_profit"]["value"], 45)
    assert saas["variable_cost_total"]["status"] == "OK"
    assert approx(saas["variable_cost_total"]["value"], 0)  # no variable items assigned -> confirmed 0
    assert approx(saas["contribution_margin"]["value"], 45)

    assert result["status"] == "OK"
    assert not result["warnings"]


# ---------------------------------------------------------------------------
# Test 9 (regression, A) — VAT-exclusive display + known VAT rate + gross-payment fee
# -> the fee must use selling_price * (1+v), not selling_price.
# ---------------------------------------------------------------------------
def test_9_gross_payment_fee_uses_vat_adjusted_base_when_price_excludes_vat():
    ci = base_input(
        product={
            "name": "VAT 제외표시 + gross-payment fee",
            "pricing_model": "one_time",
            "price_components": [base_component(actual_price=10000, price_includes_vat=False)],
        },
        costs={"items": [
            {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
             "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.05, "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "main"},
        ]},
    )
    ci["tax"]["vat_rate"] = 0.10
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["actual_price_ex_vat"]["status"] == "OK"
    assert approx(m["actual_price_ex_vat"]["value"], 10000.0)  # price_includes_vat=False -> N = selling_price

    gross_payment = 10000 * 1.10  # G = N * (1+v), NOT selling_price alone
    expected_variable = gross_payment * 0.05
    assert m["variable_cost_total"]["status"] == "OK"
    assert approx(m["variable_cost_total"]["value"], expected_variable)
    assert not approx(m["variable_cost_total"]["value"], 10000 * 0.05)  # guards against the old bug


# ---------------------------------------------------------------------------
# Test 10 (regression, B) — VAT-exclusive display + VAT rate UNKNOWN + gross-payment fee
# -> gross_profit stays OK (doesn't need gross_payment); variable_cost_total/CM/CM-rate UNKNOWN.
# ---------------------------------------------------------------------------
def test_10_gross_payment_fee_with_unknown_vat_rate_blocks_only_that_chain():
    ci = base_input(
        product={
            "name": "VAT 제외표시 + VAT율 미상 + gross-payment fee",
            "pricing_model": "one_time",
            "price_components": [base_component(actual_price=10000, price_includes_vat=False)],
        },
        costs={"items": [
            {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
             "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.05, "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "main"},
        ]},
    )
    ci["tax"]["vat_rate"] = None
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["actual_price_ex_vat"]["status"] == "OK"       # N = selling_price, v not needed here
    assert m["gross_profit"]["status"] == "OK"               # only needs N and direct cost
    assert m["variable_cost_total"]["status"] == "UNKNOWN"   # pg_fee needs G = N*(1+v), v missing
    assert m["contribution_margin"]["status"] == "UNKNOWN"
    assert m["contribution_margin_rate"]["status"] == "UNKNOWN"

    # the warning must blame tax.vat_rate, not the (perfectly known) pg_fee.rate
    var_warning = next(w for w in result["warnings"]
                        if w["metric_path"] == "mode_a.per_component.main.variable_cost_total")
    assert "tax.vat_rate" in var_warning["dependency_paths"]
    assert "costs.items[pg_fee].rate" not in var_warning["dependency_paths"]


# ---------------------------------------------------------------------------
# Test 11 (regression, C) — VAT-exclusive display + VAT rate UNKNOWN + net-sales fee only
# -> nothing needs gross_payment, so everything computes normally.
# ---------------------------------------------------------------------------
def test_11_net_sales_fee_unaffected_by_unknown_vat_rate_when_price_excludes_vat():
    ci = base_input(
        product={
            "name": "VAT 제외표시 + VAT율 미상 + net-sales fee만",
            "pricing_model": "one_time",
            "price_components": [base_component(actual_price=10000, price_includes_vat=False)],
        },
        costs={"items": [
            {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
             "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "channel_fee", "label": "채널수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.10, "currency": None, "basis": "rate_of_net_sales", "applies_to_component": "main"},
        ]},
    )
    ci["tax"]["vat_rate"] = None
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["actual_price_ex_vat"]["status"] == "OK"
    assert m["variable_cost_total"]["status"] == "OK"
    assert approx(m["variable_cost_total"]["value"], 10000 * 0.10)
    assert m["contribution_margin"]["status"] == "OK"
    assert m["contribution_margin_rate"]["status"] == "OK"


# ---------------------------------------------------------------------------
# Test 12 (regression, D) — VAT-inclusive display + VAT rate UNKNOWN
# -> net_sales_ex_vat and its dependents (gross_profit, CM, rates) are UNKNOWN, but
#    variable_cost_total stays OK when every variable item resolves via gross_payment
#    (which does NOT need v when price_includes_vat=True).
# ---------------------------------------------------------------------------
def test_12_vat_inclusive_missing_rate_blocks_net_sales_chain_not_gross_payment_chain():
    ci = base_input()  # price_includes_vat=True by default; default costs = 2 direct + pg_fee(gross_payment) + shipping(amount)
    ci["tax"]["vat_rate"] = None
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["actual_price_ex_vat"]["status"] == "UNKNOWN"
    assert m["gross_profit"]["status"] == "UNKNOWN"
    assert m["gross_profit_rate"]["status"] == "UNKNOWN"
    assert m["contribution_margin"]["status"] == "UNKNOWN"
    assert m["contribution_margin_rate"]["status"] == "UNKNOWN"

    # variable_cost_total only needs gross_payment (=selling_price when includes_vat=True,
    # no v required) and the amount-type shipping cost — neither needs vat_rate.
    assert m["variable_cost_total"]["status"] == "OK"
    assert approx(m["variable_cost_total"]["value"], 35000 * 0.025 + 3000)


# ---------------------------------------------------------------------------
# Test 13 (regression, E) — explicit VAT rate = 0 is a confirmed rate, not UNKNOWN,
# in both the ex-VAT and gross-payment directions.
# ---------------------------------------------------------------------------
def test_13_explicit_zero_vat_rate_is_not_unknown():
    ci_incl = base_input(
        product={
            "name": "VAT 0% 명시 (포함표시)",
            "pricing_model": "one_time",
            "price_components": [base_component(actual_price=10000, price_includes_vat=True)],
        },
        costs={"items": [
            {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
             "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
        ]},
    )
    ci_incl["tax"]["vat_rate"] = 0
    result_incl = run_mode_a(ci_incl)
    m_incl = result_incl["per_component"]["main"]
    assert m_incl["actual_price_ex_vat"]["status"] == "OK"
    assert approx(m_incl["actual_price_ex_vat"]["value"], 10000.0)  # 10000 / (1+0)

    ci_excl = base_input(
        product={
            "name": "VAT 0% 명시 (제외표시) + gross-payment fee",
            "pricing_model": "one_time",
            "price_components": [base_component(actual_price=10000, price_includes_vat=False)],
        },
        costs={"items": [
            {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
             "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.05, "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "main"},
        ]},
    )
    ci_excl["tax"]["vat_rate"] = 0
    result_excl = run_mode_a(ci_excl)
    m_excl = result_excl["per_component"]["main"]
    assert m_excl["variable_cost_total"]["status"] == "OK"
    assert approx(m_excl["variable_cost_total"]["value"], 10000 * (1 + 0) * 0.05)  # G = N*(1+0) = N


# ---------------------------------------------------------------------------
# Test 14 (regression, F) — applies_to_component="shared" + allocation_rule="direct" is a
# semantic contradiction (dependency_rules.md section 4) and is now ERROR /
# INVALID_ALLOCATION_CONFIGURATION in MODE A too, matching MODE B — previously MODE A accepted
# this combination "as-is" (used the cost without splitting), which is no longer the canonical
# rule: "shared" (not attributed to one component) and "direct" (already attributed to one)
# cannot both be true, so MODE A must not guess.
# ---------------------------------------------------------------------------
def test_14_shared_plus_direct_fixed_cost_is_invalid_configuration():
    ci = base_input(
        costs={"items": [
            {"item_id": "shared_direct", "label": "모순 설정: shared + direct", "cost_category": "product_service_direct_cost",
             "amount": 10000, "rate": None, "currency": "KRW", "basis": "per_unit",
             "applies_to_component": "shared", "allocation_rule": "direct"},
        ]},
    )
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["direct_cost_total"]["status"] == "ERROR"
    assert m["direct_cost_total"]["value"] is None
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_a.per_component.main.direct_cost_total")
    assert warning["code"] == "INVALID_ALLOCATION_CONFIGURATION"
    assert "costs.items[shared_direct].allocation_rule" in warning["dependency_paths"]

    # downstream metrics must propagate ERROR, never a silently-used amount
    for name in ("gross_profit", "gross_profit_rate", "contribution_margin", "contribution_margin_rate"):
        assert m[name]["status"] == "ERROR", name

    # canonical 3-tier module status (dependency_rules.md section 5): any ERROR metric -> module ERROR
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# Test 15 (regression, G) — same contradiction on a rate-based variable cost item
# (rate_of_gross_payment), within MODE A's actual supported range (a single unified
# variable_cost_total sum, unlike MODE B's separate b/a coefficients).
# ---------------------------------------------------------------------------
def test_15_shared_plus_direct_rate_based_cost_is_invalid_configuration():
    ci = base_input(
        costs={"items": [
            {"item_id": "material", "label": "자재원가", "cost_category": "product_service_direct_cost",
             "amount": 12000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "shared_pg_direct", "label": "모순 설정: shared + direct 수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.03, "currency": None, "basis": "rate_of_gross_payment",
             "applies_to_component": "shared", "allocation_rule": "direct"},
        ]},
    )
    result = run_mode_a(ci)
    m = result["per_component"]["main"]

    assert m["direct_cost_total"]["status"] == "OK"  # unaffected — different dependency chain
    assert m["variable_cost_total"]["status"] == "ERROR"
    warning = next(w for w in result["warnings"]
                   if w["metric_path"] == "mode_a.per_component.main.variable_cost_total")
    assert warning["code"] == "INVALID_ALLOCATION_CONFIGURATION"
    assert "costs.items[shared_pg_direct].allocation_rule" in warning["dependency_paths"]
    assert m["contribution_margin"]["status"] == "ERROR"
    assert result["status"] == "ERROR"


# ---------------------------------------------------------------------------
# Test 16-19 — module status must pool metrics across ALL components, not just the last one
# iterated in run_mode_a's loop, and the result must not depend on component list order.
# ---------------------------------------------------------------------------
def _two_component_ci(components_and_items, order):
    """`components_and_items`: {component_id: (component_dict, [cost_items])}. `order`: list of
    component_ids controlling price_components list order (and therefore loop iteration order)."""
    price_components = [components_and_items[cid][0] for cid in order]
    items = [item for cid in order for item in components_and_items[cid][1]]
    return {
        "schema_version": "1.1",
        "client_id": "unit_test_co",
        "case_id": "unit_test_case_multi",
        "product": {"name": "멀티 컴포넌트 테스트", "pricing_model": "hybrid", "price_components": price_components},
        "tax": {"vat_rate": 0.10},
        "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": None},
        "meta": {"entered_by": "unit_test", "entered_at": "2026-09-11", "notes": ""},
    }


def _error_and_ok_components():
    # "err": actual_price_ex_vat == 0 (price_includes_vat=False, actual_price=0) -> gross_profit
    # is OK (0 - direct_total, still a real number) but gross_profit_rate/contribution_margin_rate
    # are ERROR (division by zero) -- a genuine, already-covered MODE A ERROR path (see
    # test_13_explicit_zero_vat_rate_is_not_unknown-style cases), scoped to this component only
    # (applies_to_component="err", NOT "shared" -- a shared item would affect every component,
    # which is a different bug class already covered by tests 14/15, not what this test targets).
    err_component = {"component_id": "err", "type": "one_time", "actual_price": 0,
                      "currency": "KRW", "price_includes_vat": False}
    err_items = [{"item_id": "err_direct", "label": "원가", "cost_category": "product_service_direct_cost",
                  "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit",
                  "applies_to_component": "err"}]
    ok_component = {"component_id": "ok", "type": "one_time", "actual_price": 11000,
                     "currency": "KRW", "price_includes_vat": True}
    ok_items = [{"item_id": "ok_direct", "label": "정상원가", "cost_category": "product_service_direct_cost",
                 "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "ok"}]
    return {"err": (err_component, err_items), "ok": (ok_component, ok_items)}


def _unknown_and_ok_components():
    unk_component = {"component_id": "unk", "type": "one_time", "actual_price": 10000,
                      "currency": "KRW", "price_includes_vat": None}  # UNKNOWN -> actual_price_ex_vat UNKNOWN
    unk_items = [{"item_id": "unk_direct", "label": "원가", "cost_category": "product_service_direct_cost",
                  "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "unk"}]
    ok_component = {"component_id": "ok", "type": "one_time", "actual_price": 11000,
                     "currency": "KRW", "price_includes_vat": True}
    ok_items = [{"item_id": "ok_direct", "label": "정상원가", "cost_category": "product_service_direct_cost",
                 "amount": 4000, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "ok"}]
    return {"unk": (unk_component, unk_items), "ok": (ok_component, ok_items)}


def test_16_module_status_error_pooled_across_all_components_err_first():
    ci = _two_component_ci(_error_and_ok_components(), order=["err", "ok"])
    result = run_mode_a(ci)
    assert result["per_component"]["err"]["gross_profit_rate"]["status"] == "ERROR"
    assert result["per_component"]["ok"]["direct_cost_total"]["status"] == "OK"
    assert result["per_component"]["ok"]["gross_profit_rate"]["status"] == "OK"
    assert result["status"] == "ERROR"


def test_17_module_status_error_pooled_across_all_components_ok_first():
    # same scenario, component order reversed -> result must be identical (order-independent).
    # This is the case that would silently pass if run_mode_a only looked at the LAST
    # component's metrics instead of pooling every component (a "last-component dependency" bug).
    ci = _two_component_ci(_error_and_ok_components(), order=["ok", "err"])
    result = run_mode_a(ci)
    assert result["status"] == "ERROR"


def test_18_module_status_incomplete_pooled_across_all_components_unk_first():
    ci = _two_component_ci(_unknown_and_ok_components(), order=["unk", "ok"])
    result = run_mode_a(ci)
    assert result["per_component"]["unk"]["actual_price_ex_vat"]["status"] == "UNKNOWN"
    assert result["per_component"]["ok"]["actual_price_ex_vat"]["status"] == "OK"
    assert "ERROR" not in {m["status"] for c in result["per_component"].values() for m in c.values()}
    assert result["status"] == "INCOMPLETE"


def test_19_module_status_incomplete_pooled_across_all_components_ok_first():
    ci = _two_component_ci(_unknown_and_ok_components(), order=["ok", "unk"])
    result = run_mode_a(ci)
    assert result["status"] == "INCOMPLETE"


if __name__ == "__main__":
    # Allow `python tests/test_mode_a.py` without pytest.
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
