# -*- coding: utf-8 -*-
"""
MODE C — Allowable Direct Cost (target costing).

Pure calculation: given an externally-given market price and a target Contribution Margin Rate,
solve for the maximum product_service_direct_cost the business can still afford. Formulas and
dependency rules follow docs/features/mode_c_allowable_cost/SPEC.md v0.1 exactly — do not
diverge from it without updating that SPEC first.

Question this mode answers: "the market price is fixed and the margin target is fixed — how
much can this product actually cost to make?" MODE C never computes or suggests a price; the
market price is exogenous input, not an output (contrast with MODE B, which solves for price).

Terminology (SPEC.md sections 1-2):
    N = market_net_sales_ex_vat        (from target_market_price, via common.resolve_price_basis)
    G = market_gross_payment_incl_vat
    t = targets.target_contribution_margin_rate
    v = tax.vat_rate
    F = fixed-amount variable_selling_delivery cost (this component only)
    b = sum of rate_of_net_sales cost item rates, variable_selling_delivery only
    a = sum of rate_of_gross_payment cost item rates, variable_selling_delivery only
    ADC = allowable_direct_cost = N(1 - t - b) - aG - F = N[1 - t - b - a(1+v)] - F

Canonical market-price source (dependency_rules.md section 6): `product.price_components[]
.target_market_price` — per-component, sharing that component's own price_includes_vat/currency.
There is no `targets.target_market_price` in the schema (removed — see dependency_rules.md
section 6); MODE C has no fallback to any other field. `target_market_price` is the *effective*
(post-discount) transaction price, not a list price — MODE C does not read discount_rate.

VAT dependency is judged per metric, never as one blanket answer (SPEC.md section 6):
    - N needs v only if price_includes_vat=true (same rule as MODE A's actual_price_ex_vat).
    - G needs v only if price_includes_vat=false (same rule as MODE A's gross_payment_incl_vat).
    - allowable_direct_cost needs N always, and needs G only if a > 0 (mirrors MODE B's N/D
      dependency on `a`) — so when a=0, ADC never needs v, regardless of price_includes_vat.

Negative allowable_direct_cost is NOT an ERROR (SPEC.md section 8, dependency_rules.md section
6): unlike MODE B's N=C/D (division), ADC=N*D-F is multiplication — every combination of known,
valid inputs produces a well-defined number, including a negative one. Status stays OK, value is
preserved (never clamped to 0), and a non-blocking warning (code NEGATIVE_ALLOWABLE_COST) is
attached.

Dependency isolation (SPEC.md section 9, dependency_rules.md section 6): allowable_direct_cost
never reads product_service_direct_cost items — a problem finding/resolving actual direct-cost
data can UNKNOWN actual_direct_cost/direct_cost_gap but must never affect allowable_direct_cost,
and symmetrically a shared-cost problem in F/b/a must never affect actual_direct_cost.

Module status (dependency_rules.md section 5, canonical 3-tier): ERROR if any metric is ERROR,
else INCOMPLETE if any metric is UNKNOWN, else OK — via common.aggregate_module_status().

Shared-cost allocation (dependency_rules.md section 4): identical canonical rule to MODE A/B —
blended_only excluded, by_component_revenue/fixed_share/missing unresolved -> UNKNOWN (code
UNSUPPORTED_SHARED_COST_ALLOCATION), shared+direct -> ERROR (code
INVALID_ALLOCATION_CONFIGURATION).
"""
from __future__ import annotations

from core.engine.common import (
    ERROR,
    OK,
    UNKNOWN,
    aggregate_module_status,
    convert_to_reporting,
    metric,
    resolve_price_basis,
    warn,
)

DIRECT = "product_service_direct_cost"
VARIABLE = "variable_selling_delivery"
RATE_NET_SALES = "rate_of_net_sales"
RATE_GROSS_PAYMENT = "rate_of_gross_payment"


def _market_price_converted(component, fx):
    """(value, status, dependency_paths) for the component's target_market_price, in reporting
    currency. Mirrors mode_a.py's _price_converted / mode_b.py's price handling exactly, keyed
    to the canonical MODE C field instead of actual_price."""
    price = component.get("target_market_price")
    cid = component["component_id"]
    if price is None:
        return None, UNKNOWN, [f"product.price_components[{cid}].target_market_price"]
    value, status, dep = convert_to_reporting(price, component.get("currency"), fx)
    if status != OK:
        return None, status, [dep]
    return value, OK, []


def _classify_shared_item(item):
    """Classifies a cost item whose applies_to_component == "shared" — identical rule to
    MODE B's _classify_shared_item (dependency_rules.md section 4). Returns "excluded"
    (blended_only), "unsupported" (needs the not-yet-built blended engine -> UNKNOWN), or
    "invalid" (allocation_rule == "direct" on a shared item -> ERROR)."""
    rule = item.get("allocation_rule")
    if rule == "blended_only":
        return "excluded"
    if rule == "direct":
        return "invalid"
    return "unsupported"  # by_component_revenue / fixed_share / missing / unrecognized


def _sum_fixed_amount_variable_costs(client_input, component_id):
    """F = sum of amount-valued variable_selling_delivery items assigned directly to this
    component (never product_service_direct_cost, never fixed_operating_cost — SPEC.md section
    5/6). Rate-based items feed b/a instead. A shared item never contributes silently — see
    _classify_shared_item. (value, status, dependency_paths)."""
    fx = client_input["fx"]
    total = 0.0
    unknown_deps = []
    error_deps = []
    any_item = False

    for item in client_input["costs"]["items"]:
        if item["cost_category"] != VARIABLE:
            continue
        if item["basis"] in (RATE_NET_SALES, RATE_GROSS_PAYMENT):
            continue  # feeds b/a, not F, regardless of amount/rate nullness
        applies = item["applies_to_component"]
        if applies == component_id:
            pass
        elif applies == "shared":
            classification = _classify_shared_item(item)
            if classification == "excluded":
                continue
            any_item = True
            if classification == "invalid":
                error_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            elif item.get("allocation_rule") in ("by_component_revenue", "fixed_share"):
                unknown_deps.append(f"blended.allocation[{item['item_id']}]")
            else:
                unknown_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            continue
        else:
            continue

        any_item = True
        amount = item.get("amount")
        if amount is None:
            unknown_deps.append(f"costs.items[{item['item_id']}].amount")
            continue
        value, status, dep = convert_to_reporting(amount, item.get("currency"), fx)
        if status != OK:
            unknown_deps.append(dep or f"costs.items[{item['item_id']}].amount")
            continue
        total += value

    if not any_item:
        return 0.0, OK, []
    if error_deps:
        return None, ERROR, error_deps
    if unknown_deps:
        return None, UNKNOWN, unknown_deps
    return total, OK, []


def _sum_rate(client_input, component_id, basis):
    """b (basis=rate_of_net_sales) or a (basis=rate_of_gross_payment): sum of rate values for
    variable_selling_delivery items assigned directly to this component. No matching item is a
    confirmed 0, not UNKNOWN. A shared item never contributes silently. (value, status,
    dependency_paths)."""
    unknown_deps = []
    error_deps = []
    total = 0.0
    any_item = False
    for item in client_input["costs"]["items"]:
        if item["cost_category"] != VARIABLE:
            continue
        if item["basis"] != basis:
            continue
        applies = item["applies_to_component"]
        if applies == component_id:
            pass
        elif applies == "shared":
            classification = _classify_shared_item(item)
            if classification == "excluded":
                continue
            any_item = True
            if classification == "invalid":
                error_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            elif item.get("allocation_rule") in ("by_component_revenue", "fixed_share"):
                unknown_deps.append(f"blended.allocation[{item['item_id']}]")
            else:
                unknown_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            continue
        else:
            continue

        any_item = True
        rate = item.get("rate")
        if rate is None:
            unknown_deps.append(f"costs.items[{item['item_id']}].rate")
            continue
        total += rate
    if not any_item:
        return 0.0, OK, []
    if error_deps:
        return None, ERROR, error_deps
    if unknown_deps:
        return None, UNKNOWN, unknown_deps
    return total, OK, []


def _sum_actual_direct_cost(client_input, component_id):
    """actual_direct_cost = sum of amount-valued product_service_direct_cost items assigned to
    this component. NEVER a dependency of allowable_direct_cost (SPEC.md section 9's dependency
    isolation) — this function's result feeds only actual_direct_cost/direct_cost_gap. A shared
    item never contributes silently. (value, status, dependency_paths)."""
    fx = client_input["fx"]
    total = 0.0
    unknown_deps = []
    error_deps = []
    any_item = False

    for item in client_input["costs"]["items"]:
        if item["cost_category"] != DIRECT:
            continue
        applies = item["applies_to_component"]
        if applies == component_id:
            pass
        elif applies == "shared":
            classification = _classify_shared_item(item)
            if classification == "excluded":
                continue
            any_item = True
            if classification == "invalid":
                error_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            elif item.get("allocation_rule") in ("by_component_revenue", "fixed_share"):
                unknown_deps.append(f"blended.allocation[{item['item_id']}]")
            else:
                unknown_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            continue
        else:
            continue

        any_item = True
        amount = item.get("amount")
        if amount is None:
            unknown_deps.append(f"costs.items[{item['item_id']}].amount")
            continue
        value, status, dep = convert_to_reporting(amount, item.get("currency"), fx)
        if status != OK:
            unknown_deps.append(dep or f"costs.items[{item['item_id']}].amount")
            continue
        total += value

    if not any_item:
        return 0.0, OK, []
    if error_deps:
        return None, ERROR, error_deps
    if unknown_deps:
        return None, UNKNOWN, unknown_deps
    return total, OK, []


def compute_component(client_input, component):
    cid = component["component_id"]
    tax = client_input["tax"]
    fx = client_input["fx"]
    unit = fx["reporting_currency"]
    targets = client_input.get("targets") or {}
    v = tax.get("vat_rate")

    metrics = {}
    warnings = []

    # --- market price normalization: target_market_price -> (N, G) via common.resolve_price_basis ---
    price_value, price_status, price_deps = _market_price_converted(component, fx)
    if price_status != OK:
        n_value, n_status, n_deps = None, price_status, price_deps
        g_value, g_status, g_deps = None, price_status, price_deps
    else:
        (n_value, n_status, n_deps), (g_value, g_status, g_deps) = resolve_price_basis(
            price_value, component.get("price_includes_vat"), v, cid)

    metrics["market_net_sales_ex_vat"] = metric(n_value, n_status, unit)
    if n_status != OK:
        warnings.append(warn(
            "MISSING_DEPENDENCY", "blocking",
            f"mode_c.per_component.{cid}.market_net_sales_ex_vat", n_deps,
            "시장가격 또는 VAT 관련 필드가 미입력되어 market net sales(N)를 계산할 수 없습니다.",
        ))

    metrics["market_gross_payment_incl_vat"] = metric(g_value, g_status, unit)
    if g_status != OK:
        warnings.append(warn(
            "MISSING_DEPENDENCY", "blocking",
            f"mode_c.per_component.{cid}.market_gross_payment_incl_vat", g_deps,
            "시장가격 또는 VAT 관련 필드가 미입력되어 market gross payment(G)를 계산할 수 없습니다.",
        ))

    # --- target CM rate (t) ---
    t = targets.get("target_contribution_margin_rate")
    if t is None:
        t_status, t_deps = UNKNOWN, ["targets.target_contribution_margin_rate"]
    elif t < 0 or t >= 1:
        t_status, t_deps = ERROR, ["targets.target_contribution_margin_rate"]
    else:
        t_status, t_deps = OK, []

    # --- cost aggregates: F, b, a (variable_selling_delivery only) ---
    f_value, f_status, f_deps = _sum_fixed_amount_variable_costs(client_input, cid)
    b_value, b_status, b_deps = _sum_rate(client_input, cid, RATE_NET_SALES)
    a_value, a_status, a_deps = _sum_rate(client_input, cid, RATE_GROSS_PAYMENT)

    # --- allowable_direct_cost: ADC = N(1-t-b) - aG - F; needs G only if a > 0 ---
    error_deps = []
    unknown_deps = []
    if n_status == ERROR:
        error_deps.extend(n_deps)
    elif n_status != OK:
        unknown_deps.extend(n_deps)
    if t_status == ERROR:
        error_deps.extend(t_deps)
    elif t_status != OK:
        unknown_deps.extend(t_deps)
    if f_status == ERROR:
        error_deps.extend(f_deps)
    elif f_status != OK:
        unknown_deps.extend(f_deps)
    if b_status == ERROR:
        error_deps.extend(b_deps)
    elif b_status != OK:
        unknown_deps.extend(b_deps)
    if a_status == ERROR:
        error_deps.extend(a_deps)
    elif a_status != OK:
        unknown_deps.extend(a_deps)

    if error_deps:
        adc_value, adc_status, adc_deps = None, ERROR, error_deps
        adc_code = "INVALID_ALLOCATION_CONFIGURATION" if any(
            p.endswith(".allocation_rule") for p in error_deps
        ) else "CALCULATION_ERROR"
        adc_message = (
            "shared 비용에 allocation_rule=direct가 설정되어 있어(shared와 의미적으로 모순) "
            "허용원가(ADC)를 계산할 수 없습니다."
            if adc_code == "INVALID_ALLOCATION_CONFIGURATION"
            else "목표 CM율이 유효 범위(0 이상 1 미만)를 벗어나 허용원가(ADC)를 계산할 수 없습니다."
        )
    elif unknown_deps:
        adc_value, adc_status, adc_deps = None, UNKNOWN, unknown_deps
        adc_code = "UNSUPPORTED_SHARED_COST_ALLOCATION" if any(
            p.startswith("blended.allocation[") for p in unknown_deps
        ) else "MISSING_DEPENDENCY"
        adc_message = (
            "F/b/a 중 일부가 shared 비용이며 배부(allocation) 결과가 없어 허용원가(ADC)를 계산할 "
            "수 없습니다 (0으로 취급하지 않음)."
            if adc_code == "UNSUPPORTED_SHARED_COST_ALLOCATION"
            else "시장가격, 목표 CM율, 또는 F/b/a 중 일부가 미확정이라 허용원가(ADC)를 계산할 수 "
                 "없습니다."
        )
    elif a_value > 0 and g_status != OK:
        # a > 0 makes ADC need G, independent of whether N itself needed v (SPEC.md section 6/7).
        if g_status == ERROR:
            adc_value, adc_status, adc_deps = None, ERROR, [f"mode_c.per_component.{cid}.market_gross_payment_incl_vat"]
            adc_code, adc_message = "DOWNSTREAM_ERROR", "market gross payment(G)가 ERROR라 허용원가(ADC)를 계산할 수 없습니다."
        else:
            adc_value, adc_status, adc_deps = None, UNKNOWN, [f"mode_c.per_component.{cid}.market_gross_payment_incl_vat"]
            adc_code, adc_message = "DOWNSTREAM_UNKNOWN", "market gross payment(G)가 미확정이라 허용원가(ADC)를 계산할 수 없습니다 (gross-payment 기준 수수료가 있어 G가 필요합니다)."
    else:
        # a == 0 -> the aG term vanishes; G is never referenced, regardless of its own status.
        ag_term = a_value * g_value if a_value > 0 else 0.0
        adc_value = n_value * (1 - t - b_value) - ag_term - f_value
        adc_status, adc_deps, adc_code, adc_message = OK, [], None, None

    metrics["allowable_direct_cost"] = metric(adc_value, adc_status, unit)
    if adc_status != OK:
        warnings.append(warn(adc_code, "blocking", f"mode_c.per_component.{cid}.allowable_direct_cost", adc_deps, adc_message))
    elif adc_value < 0:
        warnings.append(warn(
            "NEGATIVE_ALLOWABLE_COST", "warning",
            f"mode_c.per_component.{cid}.allowable_direct_cost", [],
            "현재 시장가격·수수료 구조·목표 CM율로는 product/service direct cost를 0으로 낮춰도 "
            "목표를 달성할 수 없습니다 (허용원가가 음수). 목표율 재검토, 수수료 구조 재협상, "
            "또는 이 가격대 자체의 재검토가 필요합니다.",
        ))

    # --- actual_direct_cost: NEVER a dependency of allowable_direct_cost (dependency isolation) ---
    actual_value, actual_status, actual_deps = _sum_actual_direct_cost(client_input, cid)
    metrics["actual_direct_cost"] = metric(actual_value, actual_status, unit)
    if actual_status == ERROR:
        warnings.append(warn(
            "INVALID_ALLOCATION_CONFIGURATION", "blocking",
            f"mode_c.per_component.{cid}.actual_direct_cost", actual_deps,
            "shared 비용에 allocation_rule=direct가 설정되어 있어(shared와 의미적으로 모순) "
            "실제 직접원가를 계산할 수 없습니다.",
        ))
    elif actual_status == UNKNOWN:
        code = "UNSUPPORTED_SHARED_COST_ALLOCATION" if any(
            p.startswith("blended.allocation[") for p in actual_deps
        ) else "MISSING_DEPENDENCY"
        message = (
            "실제 직접원가 중 shared 비용이 있으나 배부(allocation) 결과가 없어 계산할 수 없습니다 "
            "(0으로 취급하지 않음)."
            if code == "UNSUPPORTED_SHARED_COST_ALLOCATION"
            else "상품/서비스 직접원가 항목이 미입력되어 실제 직접원가를 계산할 수 없습니다."
        )
        warnings.append(warn(code, "blocking", f"mode_c.per_component.{cid}.actual_direct_cost", actual_deps, message))

    # --- direct_cost_gap = allowable_direct_cost - actual_direct_cost ---
    if adc_status == OK and actual_status == OK:
        gap_value, gap_status, gap_deps = adc_value - actual_value, OK, []
        gap_code, gap_message = None, None
    elif adc_status == ERROR or actual_status == ERROR:
        gap_value, gap_status = None, ERROR
        gap_deps = [p for p, s in (
            (f"mode_c.per_component.{cid}.allowable_direct_cost", adc_status),
            (f"mode_c.per_component.{cid}.actual_direct_cost", actual_status),
        ) if s == ERROR]
        gap_code, gap_message = "DOWNSTREAM_ERROR", "allowable_direct_cost 또는 actual_direct_cost가 ERROR라 gap을 계산할 수 없습니다."
    else:
        gap_value, gap_status = None, UNKNOWN
        gap_deps = [p for p, s in (
            (f"mode_c.per_component.{cid}.allowable_direct_cost", adc_status),
            (f"mode_c.per_component.{cid}.actual_direct_cost", actual_status),
        ) if s != OK]
        gap_code, gap_message = "DOWNSTREAM_UNKNOWN", "allowable_direct_cost 또는 actual_direct_cost가 미확정이라 gap을 계산할 수 없습니다."

    metrics["direct_cost_gap"] = metric(gap_value, gap_status, unit)
    if gap_status != OK:
        warnings.append(warn(gap_code, "blocking", f"mode_c.per_component.{cid}.direct_cost_gap", gap_deps, gap_message))

    # --- expected_contribution_margin = N - ADC - F - bN - aG (independent self-check, NOT t*N) ---
    if adc_status == OK:
        ag_term = a_value * g_value if a_value > 0 else 0.0
        cm_value = n_value - adc_value - f_value - b_value * n_value - ag_term
        cm_status, cm_code, cm_message = OK, None, None
    elif adc_status == ERROR:
        cm_value, cm_status = None, ERROR
        cm_code, cm_message = "DOWNSTREAM_ERROR", "allowable_direct_cost가 ERROR라 예상 Contribution Margin을 계산할 수 없습니다."
    else:
        cm_value, cm_status = None, UNKNOWN
        cm_code, cm_message = "DOWNSTREAM_UNKNOWN", "allowable_direct_cost가 미확정이라 예상 Contribution Margin을 계산할 수 없습니다."

    metrics["expected_contribution_margin"] = metric(cm_value, cm_status, unit)
    if cm_status != OK:
        warnings.append(warn(cm_code, "blocking", f"mode_c.per_component.{cid}.expected_contribution_margin",
                              [f"mode_c.per_component.{cid}.allowable_direct_cost"], cm_message))

    # --- expected_contribution_margin_rate = expected_contribution_margin / N ---
    if cm_status == OK and n_value != 0:
        cmr_value, cmr_status, cmr_code, cmr_message = cm_value / n_value, OK, None, None
    elif cm_status == OK:
        # n_value == 0 but cm_status is OK only if n_status was OK -- a confirmed zero market
        # price makes the rate mathematically undefined (division by zero), not missing data.
        cmr_value, cmr_status = None, ERROR
        cmr_code, cmr_message = "CALCULATION_ERROR", "market_net_sales_ex_vat이 0이라 비율을 계산할 수 없습니다."
    elif cm_status == ERROR:
        cmr_value, cmr_status = None, ERROR
        cmr_code, cmr_message = "DOWNSTREAM_ERROR", "expected_contribution_margin이 ERROR라 비율을 계산할 수 없습니다."
    else:
        cmr_value, cmr_status = None, UNKNOWN
        cmr_code, cmr_message = "DOWNSTREAM_UNKNOWN", "expected_contribution_margin이 미확정이라 비율을 계산할 수 없습니다."

    metrics["expected_contribution_margin_rate"] = metric(cmr_value, cmr_status, "ratio")
    if cmr_status != OK:
        warnings.append(warn(cmr_code, "blocking", f"mode_c.per_component.{cid}.expected_contribution_margin_rate",
                              [f"mode_c.per_component.{cid}.expected_contribution_margin"], cmr_message))

    return metrics, warnings


def run_mode_c(client_input: dict) -> dict:
    per_component = {}
    all_warnings = []
    all_metrics = []

    for component in client_input["product"]["price_components"]:
        metrics, warnings = compute_component(client_input, component)
        per_component[component["component_id"]] = metrics
        all_warnings.extend(warnings)
        all_metrics.extend(metrics.values())

    return {
        "status": aggregate_module_status(all_metrics),
        "per_component": per_component,
        "warnings": all_warnings,
    }
