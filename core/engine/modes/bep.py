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
(SPEC.md section 5) with zero formula duplication. fixed_operating_cost aggregation (a category
MODE A never reads, with its own shared-cost semantics) is economics.sum_fixed_operating_cost,
shared with Volume Profit (docs/features/volume_profit/SPEC.md section 12).

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
    metric,
    resolve_price_basis,
    warn,
)
from core.engine.economics import (
    DIRECT,
    FIXED_COST_MESSAGES,
    VARIABLE,
    price_converted,
    sum_cost_category,
    sum_fixed_operating_cost,
)

NOT_APPLICABLE = "NOT_APPLICABLE"


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
    fc_value, fc_status, fc_code, fc_deps, analysis_period_basis = sum_fixed_operating_cost(client_input, cid)
    metrics["fixed_operating_cost"] = metric(fc_value, fc_status, unit)
    if fc_status != OK:
        warnings.append(warn(
            fc_code, "blocking", f"bep.per_component.{cid}.fixed_operating_cost", fc_deps,
            FIXED_COST_MESSAGES[fc_code],
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
