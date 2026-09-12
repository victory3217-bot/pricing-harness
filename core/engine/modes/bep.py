# -*- coding: utf-8 -*-
"""
BEP — Break-Even Point.

Pure calculation: given the current actual price's Contribution Margin structure (MODE A
semantics) and fixed_operating_cost, solve for the break-even sales quantity. Formulas and
dependency rules follow docs/features/bep/SPEC.md v0.1 exactly — do not diverge from it without
updating that SPEC first.

Question this mode answers: "현재 가격과 Contribution Margin 구조에서 고정운영비를 회수하려면
몇 단위를 판매해야 하는가?"

Terminology (SPEC.md sections 2-5):
    N   = net_sales_ex_vat (current actual price, MODE A's actual_price_ex_vat)
    CMu = contribution_margin_per_unit  (MODE A's Contribution Margin semantics exactly)
    FC  = fixed_operating_cost for the component/analysis-period being analyzed
    Q_BEP = FC / CMu

BEP takes only `client_input`, uniform with run_mode_a/b/c — it independently recomputes
CMu from the same cost-aggregation logic MODE A uses (SPEC.md section 3, "Design 2"), rather
than consuming an existing mode_a result object. To avoid duplicating that aggregation logic, both
this module and mode_a.py call the SAME shared primitives in core/engine/economics.py
(price_converted, sum_cost_category) — BEP does not depend on mode_a.py at all (no import from
it), and mode_a.py itself was migrated onto economics.py rather than keeping its own copy, so
there is exactly one implementation of direct/variable cost aggregation and VAT-basis price
conversion in the codebase, not two. This satisfies "no new price-normalization semantics"
(SPEC.md section 5) with zero formula duplication; only fixed_operating_cost aggregation (a
category MODE A never reads, with BEP-specific shared-cost semantics — see
_sum_fixed_operating_cost below) is new, BEP-local code.

Multi-component hard gate (SPEC.md section 11, dependency_rules.md section 7): more than one
product.price_components entry makes run_bep() return status=ERROR, per_component={}, and a
single MULTI_COMPONENT_BEP_NOT_SUPPORTED warning, evaluated BEFORE anything else — no
fixed-cost/CM/currency/shared-allocation evaluation is attempted in this case, not even
partially.

CMu sign semantics (SPEC.md section 6/9, dependency_rules.md section 7): break_even_quantity_exact
is NOT_APPLICABLE (value null, never a raw 0 or negative number) whenever contribution_margin_
per_unit is OK and <= 0, for every combination of FC (including FC=0) -- never inferred
post-hoc from a raw ZeroDivisionError.

Shared fixed-cost allocation (dependency_rules.md section 7): identical canonical rule to
MODE A/B/C for "direct" (ERROR, INVALID_ALLOCATION_CONFIGURATION) and
"by_component_revenue"/"fixed_share"/unrecognized (UNKNOWN, UNSUPPORTED_SHARED_COST_ALLOCATION),
but "blended_only" deviates: UNKNOWN (FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED), never the
"excluded/contributes 0" treatment every other mode gives it, because fixed_operating_cost IS
BEP's numerator.
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
from core.engine.economics import DIRECT, VARIABLE, price_converted, sum_cost_category

NOT_APPLICABLE = "NOT_APPLICABLE"
FIXED = "fixed_operating_cost"


def _sum_fixed_operating_cost(client_input, component_id):
    """(value, status, code, dependency_paths, analysis_period_basis).

    Mirrors economics.sum_cost_category's no-item/null/explicit-zero + shared-cost classification
    pattern (see that function's docstring), with BEP-specific additions — this function is
    intentionally NOT folded into economics.py (see this module's docstring and
    docs/features/bep/SPEC.md section 12):
    - amount < 0 -> ERROR, INVALID_NEGATIVE_COST (SPEC.md section 4 -- new rule, no mode before
      BEP ever needed a sign check on this field).
    - shared + allocation_rule=blended_only -> UNKNOWN, FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED
      (SPEC.md section 12 -- deviates from every other mode's "excluded, contributes 0, no
      warning" treatment, because fixed_operating_cost IS what BEP sums).
    - every contributing item's own `basis` is tracked; more than one distinct basis among
      contributing items -> ERROR, INCONSISTENT_FIXED_COST_BASIS (SPEC.md section 4/12).
    """
    fx = client_input["fx"]
    total = 0.0
    unknown_deps = []
    blended_only_deps = []
    error_deps = []
    negative_deps = []
    currency_error_deps = []
    any_item = False
    bases = set()

    for item in client_input["costs"]["items"]:
        if item["cost_category"] != FIXED:
            continue
        applies = item["applies_to_component"]

        if applies == component_id:
            pass
        elif applies == "shared":
            rule = item.get("allocation_rule")
            any_item = True
            bases.add(item["basis"])
            if rule == "direct":
                error_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
                continue
            if rule == "blended_only":
                blended_only_deps.append(f"blended.allocation[{item['item_id']}]")
                continue
            if rule in ("by_component_revenue", "fixed_share"):
                unknown_deps.append(f"blended.allocation[{item['item_id']}]")
                continue
            unknown_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            continue
        else:
            continue

        any_item = True
        bases.add(item["basis"])
        amount = item.get("amount")
        if amount is None:
            unknown_deps.append(f"costs.items[{item['item_id']}].amount")
            continue
        if amount < 0:
            negative_deps.append(f"costs.items[{item['item_id']}].amount")
            continue
        value, status, dep = convert_to_reporting(amount, item.get("currency"), fx)
        if status == ERROR:
            # Unsupported currency (SPEC.md section 13/15) -- ERROR, distinct from the plain
            # "missing fx rate" UNKNOWN convert_to_reporting can also return.
            currency_error_deps.append(dep or f"costs.items[{item['item_id']}].amount")
            continue
        if status != OK:
            unknown_deps.append(dep or f"costs.items[{item['item_id']}].amount")
            continue
        total += value

    if not any_item:
        return 0.0, OK, None, [], None

    if negative_deps:
        return None, ERROR, "INVALID_NEGATIVE_COST", negative_deps, None
    if error_deps:
        return None, ERROR, "INVALID_ALLOCATION_CONFIGURATION", error_deps, None
    if currency_error_deps:
        return None, ERROR, "UNSUPPORTED_CURRENCY", currency_error_deps, None
    if len(bases) > 1:
        return None, ERROR, "INCONSISTENT_FIXED_COST_BASIS", [], None
    if blended_only_deps:
        return None, UNKNOWN, "FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED", blended_only_deps, None
    if unknown_deps:
        code = "UNSUPPORTED_SHARED_COST_ALLOCATION" if any(
            p.startswith("blended.allocation[") for p in unknown_deps
        ) else "MISSING_DEPENDENCY"
        return None, UNKNOWN, code, unknown_deps, None

    basis = next(iter(bases)) if bases else None
    return total, OK, None, [], basis


def compute_component(client_input, component):
    cid = component["component_id"]
    tax = client_input["tax"]
    fx = client_input["fx"]
    unit = fx["reporting_currency"]

    price_value, price_status, price_deps = price_converted(component, fx)
    if price_status != OK:
        n_value, n_status, n_deps = None, price_status, price_deps
        g_value, g_status, g_deps = None, price_status, price_deps
    else:
        (n_value, n_status, n_deps), (g_value, g_status, g_deps) = resolve_price_basis(
            price_value, component.get("price_includes_vat"), tax.get("vat_rate"), cid)

    revenue_ex_vat = (n_value, n_status, n_deps)
    gross_payment = (g_value, g_status, g_deps)

    metrics = {}
    warnings = []

    # --- contribution_margin_per_unit: MODE A's CM semantics, independently recomputed ---
    direct_total, direct_status, direct_deps = sum_cost_category(
        client_input, cid, DIRECT, revenue_ex_vat, gross_payment)
    variable_total, variable_status, variable_deps = sum_cost_category(
        client_input, cid, VARIABLE, revenue_ex_vat, gross_payment)

    cm_error_deps = []
    cm_unknown_deps = []
    for status, deps in ((n_status, n_deps), (direct_status, direct_deps), (variable_status, variable_deps)):
        if status == ERROR:
            cm_error_deps.extend(deps)
        elif status != OK:
            cm_unknown_deps.extend(deps)

    if cm_error_deps:
        cmu_value, cmu_status = None, ERROR
        cmu_code = "INVALID_ALLOCATION_CONFIGURATION" if any(
            p.endswith(".allocation_rule") for p in cm_error_deps
        ) else "CALCULATION_ERROR"
        cmu_message = (
            "shared 비용에 allocation_rule=direct가 설정되어 있어 Contribution Margin per unit을 "
            "계산할 수 없습니다." if cmu_code == "INVALID_ALLOCATION_CONFIGURATION" else
            "가격/VAT 관련 필드에 오류가 있어 Contribution Margin per unit을 계산할 수 없습니다."
        )
    elif cm_unknown_deps:
        cmu_value, cmu_status = None, UNKNOWN
        cmu_code = "MISSING_DEPENDENCY"
        cmu_message = (
            "판매가/VAT 또는 직접원가·변동비 항목이 미입력되었거나 공유비용 배부 규칙이 아직 "
            "지원되지 않아 단위당 Contribution Margin을 계산할 수 없습니다."
        )
    else:
        cmu_value = n_value - direct_total - variable_total
        cmu_status, cmu_code, cmu_message = OK, None, None

    metrics["contribution_margin_per_unit"] = metric(cmu_value, cmu_status, unit)
    if cmu_status != OK:
        warnings.append(warn(
            cmu_code, "blocking", f"bep.per_component.{cid}.contribution_margin_per_unit",
            cm_error_deps or cm_unknown_deps, cmu_message,
        ))

    # --- fixed_operating_cost: independent aggregation, never reads product_service_direct_cost
    #     or any prior mode_a/mode_b/mode_c output ---
    fc_value, fc_status, fc_code, fc_deps, analysis_period_basis = _sum_fixed_operating_cost(client_input, cid)
    metrics["fixed_operating_cost"] = metric(fc_value, fc_status, unit)
    if fc_status != OK:
        fc_messages = {
            "INVALID_NEGATIVE_COST": "fixed_operating_cost 항목의 금액이 음수입니다 — 유효한 비용으로 취급하지 않습니다.",
            "INVALID_ALLOCATION_CONFIGURATION": "shared 비용에 allocation_rule=direct가 설정되어 있어 fixed_operating_cost를 계산할 수 없습니다.",
            "UNSUPPORTED_CURRENCY": "fixed_operating_cost 항목의 통화를 reporting currency로 환산할 수 없습니다 (미지원 통화).",
            "INCONSISTENT_FIXED_COST_BASIS": "이 컴포넌트에 귀속되는 fixed_operating_cost 항목들의 basis(분석기간)가 서로 달라 합산할 수 없습니다.",
            "FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED": "fixed_operating_cost 항목이 blended_only로 설정되어 있어(컴포넌트별 배부 대상이 아님) 아직 배부되지 않았습니다 — 0으로 취급하지 않습니다.",
            "UNSUPPORTED_SHARED_COST_ALLOCATION": "fixed_operating_cost 중 shared 비용이 있으나 배부(allocation) 결과가 없어 계산할 수 없습니다 (0으로 취급하지 않음).",
            "MISSING_DEPENDENCY": "fixed_operating_cost 항목이 미입력되어 계산할 수 없습니다.",
        }
        warnings.append(warn(
            fc_code, "blocking", f"bep.per_component.{cid}.fixed_operating_cost", fc_deps,
            fc_messages[fc_code],
        ))

    # --- break_even_quantity_exact = FC / CMu ---
    if cmu_status == ERROR or fc_status == ERROR:
        q_value, q_status = None, ERROR
        q_deps = [p for p, s in (
            (f"bep.per_component.{cid}.contribution_margin_per_unit", cmu_status),
            (f"bep.per_component.{cid}.fixed_operating_cost", fc_status),
        ) if s == ERROR]
        q_code, q_message = "DOWNSTREAM_ERROR", "contribution_margin_per_unit 또는 fixed_operating_cost가 ERROR라 손익분기 판매량을 계산할 수 없습니다."
    elif cmu_status != OK or fc_status != OK:
        q_value, q_status = None, UNKNOWN
        q_deps = [p for p, s in (
            (f"bep.per_component.{cid}.contribution_margin_per_unit", cmu_status),
            (f"bep.per_component.{cid}.fixed_operating_cost", fc_status),
        ) if s != OK]
        q_code, q_message = "DOWNSTREAM_UNKNOWN", "contribution_margin_per_unit 또는 fixed_operating_cost가 미확정이라 손익분기 판매량을 계산할 수 없습니다."
    elif cmu_value == 0:
        q_value, q_status = None, NOT_APPLICABLE
        q_deps = []
        if fc_value == 0:
            q_code = "BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST"
            q_message = "고정비와 단위 마진이 모두 0입니다 — 손익분기 판매량이라는 개념이 정의되지 않습니다 (0/0)."
        else:
            q_code = "BREAK_EVEN_UNDEFINED_ZERO_MARGIN"
            q_message = "현재 단위 마진이 0이라 어떤 판매량으로도 고정비를 회수할 수 없습니다."
    elif cmu_value < 0:
        q_value, q_status = None, NOT_APPLICABLE
        q_deps = []
        q_code = "BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN"
        q_message = "판매할수록 손실이 커지는 구조입니다(단위 마진 음수). 이 가격·비용구조에서는 손익분기 판매량이라는 개념 자체가 성립하지 않습니다."
    else:
        q_value, q_status, q_code, q_message = fc_value / cmu_value, OK, None, []

    metrics["break_even_quantity_exact"] = metric(q_value, q_status, "units")
    if q_status == NOT_APPLICABLE:
        warnings.append(warn(q_code, "warning", f"bep.per_component.{cid}.break_even_quantity_exact", [], q_message))
    elif q_status != OK:
        warnings.append(warn(q_code, "blocking", f"bep.per_component.{cid}.break_even_quantity_exact", q_deps, q_message))

    return metrics, warnings, analysis_period_basis


def run_bep(client_input: dict) -> dict:
    components = client_input["product"]["price_components"]

    if len(components) > 1:
        return {
            "status": ERROR,
            "per_component": {},
            "warnings": [warn(
                "MULTI_COMPONENT_BEP_NOT_SUPPORTED", "blocking", "bep",
                ["product.price_components"],
                "BEP v0.1은 단일 컴포넌트 상품만 지원합니다 — 이 Client Input은 컴포넌트가 2개 "
                "이상이라 계산하지 않습니다 (shared fixed cost 이중계상 방지).",
            )],
        }

    per_component = {}
    all_warnings = []
    all_metrics = []

    for component in components:
        cid = component["component_id"]
        metrics, warnings, analysis_period_basis = compute_component(client_input, component)
        per_component[cid] = {
            "analysis_period_basis": analysis_period_basis,
            **metrics,
        }
        all_warnings.extend(warnings)
        all_metrics.extend(metrics.values())

    return {
        "status": aggregate_module_status(all_metrics),
        "per_component": per_component,
        "warnings": all_warnings,
    }
