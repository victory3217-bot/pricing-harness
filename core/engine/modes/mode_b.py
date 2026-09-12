# -*- coding: utf-8 -*-
"""
MODE B — Target Price (reverse calculation).

Pure calculation: given a target Contribution Margin Rate and the same cost/fee structure
MODE A reads, solve for the price that hits that target. Formulas and VAT-dependency rules
follow docs/features/mode_b_target_price/SPEC.md v0.2 exactly — do not diverge from it without
updating that SPEC first.

Terminology (SPEC.md sections 1-2):
    C = fixed-amount direct + variable costs (money-valued, this component only)
    b = sum of rate_of_net_sales cost item rates (this component only)
    a = sum of rate_of_gross_payment cost item rates (this component only)
    t = targets.target_contribution_margin_rate
    v = tax.vat_rate
    N = required_net_sales_ex_vat      = C / [1 - t - b - a(1+v)]
    G = required_gross_payment_incl_vat = N * (1 + v)

VAT dependency is judged per metric, never as one blanket answer (SPEC.md section 3):
    - required_net_sales_ex_vat (N): needs v only if a > 0.
    - required_gross_payment_incl_vat (G): always needs v, independent of a.
    - required_selling_price: reads N if price_includes_vat is false, G if true, UNKNOWN if
      price_includes_vat is null — so it inherits whichever of N/G's dependency rule applies.

denominator <= 0 is a confirmed ERROR (target unreachable at any price), not UNKNOWN — it
propagates downstream as ERROR (code DOWNSTREAM_ERROR), distinct from a missing-input UNKNOWN.

Out of scope for this step (see SPEC.md "Explicitly out of scope"): tax-exempt/zero-rated/
multi-rate VAT, blended economics (the whole-contract engine that actually performs
by_component_revenue / fixed_share allocation). A cost item with applies_to_component ==
"shared" is NOT silently excluded, though — that would understate C/b/a and report a target
price lower than the business actually needs, in violation of the Harness's null != 0 /
"UNKNOWN over a plausible-looking number" principle. `allocation_rule` on a shared item is
classified as (see core/schemas/dependency_rules.md section 4 for the underlying rule):
    - "blended_only": legitimately never appears at component level (by schema design) —
      excluded, no warning.
    - "by_component_revenue" / "fixed_share" / missing / unrecognized: this component's share of
      that cost cannot be computed without the (not-yet-built) blended engine — the affected
      aggregate (C, b, or a) becomes UNKNOWN, not 0, and every metric downstream of it becomes
      UNKNOWN too (code UNSUPPORTED_SHARED_COST_ALLOCATION). Distinct from a missing-input
      UNKNOWN, so its dependency path (blended.allocation[...]) is deliberately excluded from
      meta.missing_input_paths by result_builder.py.
    - "direct": semantically CONTRADICTORY on a shared item, not a valid "use as-is" shortcut.
      "shared" means "not attributed to one component"; "direct" (per dependency_rules.md
      section 4) means "already scoped to a specific component, just tagged shared for
      bookkeeping". A cost item cannot honestly be both. MODE B refuses to guess which one was
      meant and reports the affected aggregate as ERROR (code
      INVALID_ALLOCATION_CONFIGURATION) rather than quietly applying the full cost to every
      component that reads it (which would double- or triple-count a genuinely shared cost
      across components) or to none (which would understate it, the same failure this whole
      shared-cost handling exists to prevent).

Module status (dependency_rules.md section 5, canonical 3-tier): ERROR if any metric is ERROR,
else INCOMPLETE if any metric is UNKNOWN, else OK — via common.aggregate_module_status().
"""
from __future__ import annotations

from core.engine.common import ERROR, OK, UNKNOWN, aggregate_module_status, convert_to_reporting, metric, warn

DIRECT = "product_service_direct_cost"
VARIABLE = "variable_selling_delivery"
RATE_NET_SALES = "rate_of_net_sales"
RATE_GROSS_PAYMENT = "rate_of_gross_payment"


def _classify_shared_item(item):
    """Classifies a cost item whose applies_to_component == "shared", per the module docstring
    and core/schemas/dependency_rules.md section 4. Returns one of:
        "excluded"    - allocation_rule == "blended_only": legitimately never appears at
                        component level; caller should skip it silently.
        "unsupported" - "by_component_revenue" / "fixed_share" / missing / unrecognized rule:
                        needs the not-yet-built blended engine -> affected aggregate is UNKNOWN.
        "invalid"     - allocation_rule == "direct": semantically contradictory on a shared item
                        (see docstring) -> affected aggregate is ERROR, not silently applied.
    Never returns a "use as-is" resolution — "shared" items always require either the blended
    engine or a configuration fix, never a silent per-component application.
    """
    rule = item.get("allocation_rule")
    if rule == "blended_only":
        return "excluded"
    if rule == "direct":
        return "invalid"
    return "unsupported"  # by_component_revenue / fixed_share / missing / unrecognized


def _sum_fixed_amount_costs(client_input, component_id):
    """C = sum of amount-valued product_service_direct_cost + variable_selling_delivery items
    assigned directly to this component. A 'shared' item of the same kind never contributes
    silently (see _classify_shared_item) — 'unsupported' makes C UNKNOWN, 'invalid' makes C
    ERROR; neither is dropped as if it were 0. Rate-based items feed b/a instead (see _sum_rate).
    (value, status, dependency_paths)."""
    fx = client_input["fx"]
    total = 0.0
    unknown_deps = []
    error_deps = []
    any_item = False

    for item in client_input["costs"]["items"]:
        if item["cost_category"] not in (DIRECT, VARIABLE):
            continue
        if item["basis"] in (RATE_NET_SALES, RATE_GROSS_PAYMENT):
            continue  # this item belongs to b/a by basis, not C, regardless of amount/rate nullness
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
    variable_selling_delivery items assigned directly to this component. A 'shared' item of the
    same basis never contributes silently (see _classify_shared_item) — 'unsupported' makes this
    aggregate UNKNOWN, 'invalid' makes it ERROR. No matching item at all is a confirmed 0.
    (value, status, dependency_paths)."""
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


def _is_shared_allocation_dep(path):
    return path.startswith("blended.allocation[") or path.endswith(".allocation_rule")


def _aggregate_unknown_code(deps):
    """MISSING_DEPENDENCY for an ordinary missing field; UNSUPPORTED_SHARED_COST_ALLOCATION
    when the UNKNOWN is (at least partly) caused by an unresolved shared-cost item, so a
    consultant doesn't mistake 'the blended engine isn't built yet' for 'a client forgot to
    enter a number'."""
    if any(_is_shared_allocation_dep(p) for p in deps):
        return "UNSUPPORTED_SHARED_COST_ALLOCATION"
    return "MISSING_DEPENDENCY"


def compute_component(client_input, component):
    cid = component["component_id"]
    tax = client_input["tax"]
    fx = client_input["fx"]
    unit = fx["reporting_currency"]
    targets = client_input.get("targets") or {}
    v = tax.get("vat_rate")

    metrics = {}
    warnings = []

    # --- target CM rate (t) ---
    t = targets.get("target_contribution_margin_rate")
    t_status = OK if t is not None else UNKNOWN
    t_deps = [] if t_status == OK else ["targets.target_contribution_margin_rate"]

    # --- cost aggregates: C, b, a ---
    c_value, c_status, c_deps = _sum_fixed_amount_costs(client_input, cid)
    b_value, b_status, b_deps = _sum_rate(client_input, cid, RATE_NET_SALES)
    a_value, a_status, a_deps = _sum_rate(client_input, cid, RATE_GROSS_PAYMENT)

    # --- denominator D = 1 - t - b - a(1+v); v only needed if a > 0 ---
    # d_cause distinguishes the two ways D can end up ERROR: an invalid shared+direct config in
    # b/a (surfaced immediately, before D is even evaluated) vs. a mathematically valid D <= 0.
    # These need different codes/messages, so the cause is tracked explicitly rather than
    # re-inferred from d_value afterward.
    unknown_deps = []
    error_deps = []
    if t_status != OK:
        unknown_deps.extend(t_deps)
    if b_status == ERROR:
        error_deps.extend(b_deps)
    elif b_status != OK:
        unknown_deps.extend(b_deps)
    if a_status == ERROR:
        error_deps.extend(a_deps)
    elif a_status != OK:
        unknown_deps.extend(a_deps)

    if error_deps:
        d_value, d_status, d_deps, d_cause = None, ERROR, error_deps, "invalid_allocation"
    elif unknown_deps:
        d_value, d_status, d_deps, d_cause = None, UNKNOWN, unknown_deps, None
    elif a_value == 0:
        d_value, d_status, d_deps, d_cause = 1 - t - b_value, OK, [], None
    elif v is None:
        d_value, d_status, d_deps, d_cause = None, UNKNOWN, ["tax.vat_rate"], None
    else:
        d_value, d_status, d_deps, d_cause = 1 - t - b_value - a_value * (1 + v), OK, [], None

    if d_status == OK and d_value <= 0:
        d_status, d_cause = ERROR, "denominator_le_zero"

    metrics["denominator"] = metric(d_value, d_status, "ratio")
    if d_status == UNKNOWN:
        d_code = _aggregate_unknown_code(d_deps)
        d_message = (
            "net-sales/gross-payment 수수료율 중 일부가 shared 비용이며 배부(allocation) 결과가 "
            "없어 분모를 계산할 수 없습니다 (0으로 취급하지 않음)."
            if d_code == "UNSUPPORTED_SHARED_COST_ALLOCATION"
            else "목표 CM율, net-sales/gross-payment 수수료율, 또는 VAT율이 미입력되어 분모를 "
                 "계산할 수 없습니다."
        )
        warnings.append(warn(d_code, "blocking", f"mode_b.per_component.{cid}.denominator", d_deps, d_message))
    elif d_status == ERROR:
        if d_cause == "invalid_allocation":
            d_code = "INVALID_ALLOCATION_CONFIGURATION"
            d_message = (
                "net-sales/gross-payment 수수료율 중 shared 비용에 allocation_rule=direct가 "
                "설정되어 있습니다. 'shared'(특정 component에 귀속되지 않음)와 'direct'(이미 "
                "특정 component에 귀속됨)는 의미적으로 모순되어 분모를 계산할 수 없습니다."
            )
        else:
            d_code = "CALCULATION_ERROR"
            d_message = (
                "목표 CM율과 현재 비율형 비용 구조로는 어떤 가격을 매겨도 목표를 달성할 수 "
                "없습니다 (분모 <= 0)."
            )
        warnings.append(warn(d_code, "blocking", f"mode_b.per_component.{cid}.denominator", d_deps, d_message))

    # --- required_net_sales_ex_vat (N) ---
    # n_code/n_message are set per-branch (same reasoning as required_list_price below): N's
    # ERROR can come from either C's own currency conversion or from the denominator, and the
    # warning must name whichever one actually happened, not be inferred afterward.
    if c_status == ERROR:
        n_value, n_status, n_deps = None, ERROR, c_deps
        n_code = "INVALID_ALLOCATION_CONFIGURATION"
        n_message = (
            "직접원가/변동비 중 shared 비용에 allocation_rule=direct가 설정되어 있습니다. "
            "'shared'와 'direct'는 의미적으로 모순되어 목표 순매출(N)을 계산할 수 없습니다."
        )
    elif c_status == UNKNOWN:
        n_value, n_status, n_deps = None, UNKNOWN, c_deps
        n_code = _aggregate_unknown_code(c_deps)
        n_message = (
            "직접원가/변동비 중 shared 비용이 있으나 배부(allocation) 결과가 없어 목표 "
            "순매출(N)을 계산할 수 없습니다 (0으로 취급하지 않음)."
            if n_code == "UNSUPPORTED_SHARED_COST_ALLOCATION"
            else "직접원가/변동비 합계가 미확정이라 목표 순매출(N)을 계산할 수 없습니다."
        )
    elif d_status == UNKNOWN:
        n_value, n_status, n_deps = None, UNKNOWN, [f"mode_b.per_component.{cid}.denominator"]
        n_code = "DOWNSTREAM_UNKNOWN"
        n_message = "분모가 미확정이라 목표 순매출(N)을 계산할 수 없습니다."
    elif d_status == ERROR:
        n_value, n_status, n_deps = None, ERROR, [f"mode_b.per_component.{cid}.denominator"]
        n_code = "DOWNSTREAM_ERROR"
        n_message = "분모가 ERROR라 목표 순매출(N)을 계산할 수 없습니다."
    else:
        n_value, n_status, n_deps = c_value / d_value, OK, []
        n_code, n_message = None, None

    metrics["required_net_sales_ex_vat"] = metric(n_value, n_status, unit)
    if n_status != OK:
        warnings.append(warn(n_code, "blocking", f"mode_b.per_component.{cid}.required_net_sales_ex_vat", n_deps, n_message))

    # --- required_gross_payment_incl_vat (G): always needs v, independent of a ---
    if n_status == ERROR:
        g_value, g_status, g_deps = None, ERROR, [f"mode_b.per_component.{cid}.required_net_sales_ex_vat"]
    elif n_status == UNKNOWN:
        g_value, g_status, g_deps = None, UNKNOWN, [f"mode_b.per_component.{cid}.required_net_sales_ex_vat"]
    elif v is None:
        g_value, g_status, g_deps = None, UNKNOWN, ["tax.vat_rate"]
    else:
        g_value, g_status, g_deps = n_value * (1 + v), OK, []

    metrics["required_gross_payment_incl_vat"] = metric(g_value, g_status, unit)
    if g_status == UNKNOWN:
        code = "MISSING_DEPENDENCY" if n_status == OK else "DOWNSTREAM_UNKNOWN"
        warnings.append(warn(
            code, "blocking",
            f"mode_b.per_component.{cid}.required_gross_payment_incl_vat", g_deps,
            "VAT율(또는 목표 순매출)이 미확정이라 목표 총지불금액(G)을 계산할 수 없습니다.",
        ))
    elif g_status == ERROR:
        warnings.append(warn(
            "DOWNSTREAM_ERROR", "blocking",
            f"mode_b.per_component.{cid}.required_gross_payment_incl_vat", g_deps,
            "목표 순매출(N)이 ERROR라 목표 총지불금액(G)을 계산할 수 없습니다.",
        ))

    # --- required_selling_price: N if price_includes_vat=false, G if true, UNKNOWN if null ---
    includes_vat = component.get("price_includes_vat")
    if includes_vat is None:
        s_value, s_status, s_deps = None, UNKNOWN, [f"product.price_components[{cid}].price_includes_vat"]
    elif includes_vat is False:
        s_value, s_status = n_value, n_status
        s_deps = [] if n_status == OK else [f"mode_b.per_component.{cid}.required_net_sales_ex_vat"]
    else:
        s_value, s_status = g_value, g_status
        s_deps = [] if g_status == OK else [f"mode_b.per_component.{cid}.required_gross_payment_incl_vat"]

    metrics["required_selling_price"] = metric(s_value, s_status, unit)
    if s_status == UNKNOWN:
        code = "MISSING_DEPENDENCY" if includes_vat is None else "DOWNSTREAM_UNKNOWN"
        warnings.append(warn(
            code, "blocking",
            f"mode_b.per_component.{cid}.required_selling_price", s_deps,
            "표시가격 기준(price_includes_vat)이 미정이거나, 그 기준이 가리키는 지표(N/G)가 "
            "미확정이라 목표 판매가를 결정할 수 없습니다.",
        ))
    elif s_status == ERROR:
        warnings.append(warn(
            "DOWNSTREAM_ERROR", "blocking",
            f"mode_b.per_component.{cid}.required_selling_price", s_deps,
            "표시가격 기준이 가리키는 지표(N/G)가 ERROR라 목표 판매가를 결정할 수 없습니다.",
        ))

    # --- required_list_price = required_selling_price / (1 - discount_rate) ---
    # l_code/l_message are set per-branch (not inferred afterward from discount_rate) so the
    # warning always names the actual cause, even when required_selling_price is itself
    # UNKNOWN/ERROR *and* discount_rate happens to also be missing.
    discount_rate = component.get("discount_rate")
    if s_status == ERROR:
        l_value, l_status, l_deps = None, ERROR, [f"mode_b.per_component.{cid}.required_selling_price"]
        l_code = "DOWNSTREAM_ERROR"
        l_message = "목표 판매가가 ERROR라 목표 정가를 계산할 수 없습니다."
    elif s_status == UNKNOWN:
        l_value, l_status, l_deps = None, UNKNOWN, [f"mode_b.per_component.{cid}.required_selling_price"]
        l_code = "DOWNSTREAM_UNKNOWN"
        l_message = "목표 판매가가 미확정이라 목표 정가를 계산할 수 없습니다."
    elif discount_rate is None:
        l_value, l_status, l_deps = None, UNKNOWN, [f"product.price_components[{cid}].discount_rate"]
        l_code = "MISSING_DEPENDENCY"
        l_message = "할인율이 미입력되어 목표 정가를 계산할 수 없습니다."
    elif discount_rate < 0 or discount_rate >= 1:
        l_value, l_status, l_deps = None, ERROR, []
        l_code = "CALCULATION_ERROR"
        l_message = "할인율이 0 이상 1 미만 범위를 벗어나 목표 정가를 계산할 수 없습니다."
    elif discount_rate == 0:
        l_value, l_status, l_deps = s_value, OK, []
        l_code, l_message = None, None
    else:
        l_value, l_status, l_deps = s_value / (1 - discount_rate), OK, []
        l_code, l_message = None, None

    metrics["required_list_price"] = metric(l_value, l_status, unit)
    if l_status != OK:
        warnings.append(warn(l_code, "blocking", f"mode_b.per_component.{cid}.required_list_price", l_deps, l_message))

    # --- expected_contribution_margin = t * N (self-check target) ---
    if n_status == OK:
        cm_value, cm_status = t * n_value, OK
    elif n_status == ERROR:
        cm_value, cm_status = None, ERROR
    else:
        cm_value, cm_status = None, UNKNOWN
    metrics["expected_contribution_margin"] = metric(cm_value, cm_status, unit)
    if cm_status != OK:
        code = "DOWNSTREAM_ERROR" if cm_status == ERROR else "DOWNSTREAM_UNKNOWN"
        warnings.append(warn(
            code, "blocking",
            f"mode_b.per_component.{cid}.expected_contribution_margin",
            [f"mode_b.per_component.{cid}.required_net_sales_ex_vat"],
            "목표 순매출(N)이 미확정/ERROR라 예상 Contribution Margin을 계산할 수 없습니다.",
        ))

    # --- expected_contribution_margin_rate: should equal t exactly when OK (self-check) ---
    if cm_status == OK and n_value != 0:
        cmr_value, cmr_status = cm_value / n_value, OK
    elif cm_status == ERROR:
        cmr_value, cmr_status = None, ERROR
    else:
        cmr_value, cmr_status = None, UNKNOWN
    metrics["expected_contribution_margin_rate"] = metric(cmr_value, cmr_status, "ratio")
    if cmr_status != OK:
        code = "DOWNSTREAM_ERROR" if cmr_status == ERROR else "DOWNSTREAM_UNKNOWN"
        warnings.append(warn(
            code, "blocking",
            f"mode_b.per_component.{cid}.expected_contribution_margin_rate",
            [f"mode_b.per_component.{cid}.expected_contribution_margin"],
            "예상 Contribution Margin이 미확정/ERROR라 비율을 계산할 수 없습니다.",
        ))

    return metrics, warnings


def run_mode_b(client_input: dict) -> dict:
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
