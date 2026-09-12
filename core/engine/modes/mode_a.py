# -*- coding: utf-8 -*-
"""
MODE A — Current Price Diagnosis.

Pure calculation: a validated Client Input -> per-component MODE A metrics, following
core/schemas/dependency_rules.md. No client-specific logic, no company names.

Question this mode answers: "at the current price, how much is actually left on one unit
of this transaction?"

VAT handling (corrected — see docs/features/mode_a_current_price/SPEC.md and
core/schemas/dependency_rules.md section 2): a taxable transaction's gross payment is always
net_sales_ex_vat * (1 + vat_rate), regardless of how the price happens to be displayed/quoted.
`price_includes_vat` only decides which of {net_sales_ex_vat, gross_payment_incl_vat} the raw
`actual_price` field directly represents — it never makes VAT rate irrelevant to the *other*
one. This is computed via common.resolve_price_basis(), shared with any future mode that needs
the same forward (price -> N, G) direction.

Module status (dependency_rules.md section 5, canonical 3-tier): ERROR if any metric is ERROR,
else INCOMPLETE if any metric is UNKNOWN, else OK — via common.aggregate_module_status().

Shared-cost allocation (dependency_rules.md section 4): a cost item with
applies_to_component == "shared" and allocation_rule == "direct" is a semantic contradiction
("shared" = not attributed to one component; "direct" = already attributed to one) and is
treated as ERROR (code INVALID_ALLOCATION_CONFIGURATION) — the same rule MODE B applies. This
was previously accepted "as-is" by MODE A; that behavior is now removed so the same schema
field cannot mean two different things depending on which mode reads it.
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
from core.engine.economics import DIRECT, VARIABLE, price_converted, sum_cost_category

NOT_APPLICABLE = "NOT_APPLICABLE"
# ESTIMATED is part of the schema's metric_status enum but is not produced by this
# implementation yet — MODE A never substitutes an assumed value for a missing one.

FIXED = "fixed_operating_cost"  # noqa: F841  (excluded by design; kept for readability/reference)

# price_converted/sum_cost_category (core/engine/economics.py) are the shared implementations —
# MODE A and BEP (core/engine/modes/bep.py) both call them directly; this module keeps no local
# copy. See economics.py's module docstring for what is and isn't shared this way.


def compute_component(client_input, component):
    cid = component["component_id"]
    tax = client_input["tax"]
    fx = client_input["fx"]
    unit = fx["reporting_currency"]

    price_value, price_status, price_deps = price_converted(component, fx)
    if price_status != OK:
        ex_vat_value, ex_vat_status, ex_vat_deps = None, price_status, price_deps
        gross_payment_value, gross_payment_status, gross_payment_deps = None, price_status, price_deps
    else:
        (ex_vat_value, ex_vat_status, ex_vat_deps), (gross_payment_value, gross_payment_status, gross_payment_deps) = (
            resolve_price_basis(price_value, component.get("price_includes_vat"), tax.get("vat_rate"), cid)
        )

    metrics = {}
    warnings = []

    metrics["actual_price_ex_vat"] = metric(ex_vat_value, ex_vat_status, unit)
    if ex_vat_status != OK:
        warnings.append(warn(
            "MISSING_DEPENDENCY", "blocking",
            f"mode_a.per_component.{cid}.actual_price_ex_vat", ex_vat_deps,
            "VAT 관련 필드(또는 통화 환율)가 미입력되어 VAT 제외 순매출을 계산할 수 없습니다.",
        ))

    revenue_ex_vat = (ex_vat_value, ex_vat_status, ex_vat_deps)
    gross_payment = (gross_payment_value, gross_payment_status, gross_payment_deps)

    direct_total, direct_status, direct_deps = sum_cost_category(
        client_input, cid, DIRECT, revenue_ex_vat, gross_payment)
    metrics["direct_cost_total"] = metric(direct_total, direct_status, unit)
    if direct_status == ERROR:
        warnings.append(warn(
            "INVALID_ALLOCATION_CONFIGURATION", "blocking",
            f"mode_a.per_component.{cid}.direct_cost_total", direct_deps,
            "shared 비용에 allocation_rule=direct가 설정되어 있습니다. 'shared'(특정 component에 "
            "귀속되지 않음)와 'direct'(이미 특정 component에 귀속됨)는 의미적으로 모순되어 "
            "직접원가 합계를 계산할 수 없습니다.",
        ))
    elif direct_status != OK:
        warnings.append(warn(
            "MISSING_DEPENDENCY", "blocking",
            f"mode_a.per_component.{cid}.direct_cost_total", direct_deps,
            "상품/서비스 직접원가 항목이 미입력되어 직접원가 합계를 계산할 수 없습니다.",
        ))

    if ex_vat_status == OK and direct_status == OK:
        gp_value, gp_status = ex_vat_value - direct_total, OK
    elif ex_vat_status == ERROR or direct_status == ERROR:
        gp_value, gp_status = None, ERROR
    else:
        gp_value, gp_status = None, UNKNOWN
    metrics["gross_profit"] = metric(gp_value, gp_status, unit)
    if gp_status != OK:
        dep_paths = [p for p, s in (
            (f"mode_a.per_component.{cid}.actual_price_ex_vat", ex_vat_status),
            (f"mode_a.per_component.{cid}.direct_cost_total", direct_status),
        ) if s != OK]
        code = "DOWNSTREAM_ERROR" if gp_status == ERROR else "DOWNSTREAM_UNKNOWN"
        warnings.append(warn(
            code, "blocking",
            f"mode_a.per_component.{cid}.gross_profit", dep_paths,
            "상위 지표가 UNKNOWN 또는 ERROR라 gross_profit을 계산할 수 없습니다.",
        ))

    if gp_status == OK and ex_vat_status == OK and ex_vat_value != 0:
        gpr_value, gpr_status, gpr_code, gpr_message = gp_value / ex_vat_value, OK, None, None
    elif gp_status == ERROR or ex_vat_status == ERROR:
        gpr_value, gpr_status = None, ERROR
        gpr_code = "DOWNSTREAM_ERROR"
        gpr_message = "gross_profit 또는 actual_price_ex_vat이 ERROR라 비율을 계산할 수 없습니다."
    elif gp_status == OK and ex_vat_status == OK:
        gpr_value, gpr_status = None, ERROR
        gpr_code = "CALCULATION_ERROR"
        gpr_message = "actual_price_ex_vat이 0이라 비율을 계산할 수 없습니다."
    else:
        gpr_value, gpr_status = None, UNKNOWN
        gpr_code = "DOWNSTREAM_UNKNOWN"
        gpr_message = "gross_profit 또는 actual_price_ex_vat이 확정되지 않아 비율을 계산할 수 없습니다."
    metrics["gross_profit_rate"] = metric(gpr_value, gpr_status, "ratio")
    if gpr_status != OK:
        warnings.append(warn(
            gpr_code, "blocking",
            f"mode_a.per_component.{cid}.gross_profit_rate",
            [f"mode_a.per_component.{cid}.gross_profit", f"mode_a.per_component.{cid}.actual_price_ex_vat"],
            gpr_message,
        ))

    variable_total, variable_status, variable_deps = sum_cost_category(
        client_input, cid, VARIABLE, revenue_ex_vat, gross_payment)
    metrics["variable_cost_total"] = metric(variable_total, variable_status, unit)
    if variable_status == ERROR:
        warnings.append(warn(
            "INVALID_ALLOCATION_CONFIGURATION", "blocking",
            f"mode_a.per_component.{cid}.variable_cost_total", variable_deps,
            "shared 비용에 allocation_rule=direct가 설정되어 있습니다. 'shared'(특정 component에 "
            "귀속되지 않음)와 'direct'(이미 특정 component에 귀속됨)는 의미적으로 모순되어 "
            "변동비 합계를 계산할 수 없습니다.",
        ))
    elif variable_status != OK:
        warnings.append(warn(
            "MISSING_DEPENDENCY", "blocking",
            f"mode_a.per_component.{cid}.variable_cost_total", variable_deps,
            "판매/배송 변동비 항목이 미입력되었거나 공유비용 배부 규칙이 아직 지원되지 않아 "
            "변동비 합계를 계산할 수 없습니다.",
        ))

    if gp_status == OK and variable_status == OK:
        cm_value, cm_status = gp_value - variable_total, OK
    elif gp_status == ERROR or variable_status == ERROR:
        cm_value, cm_status = None, ERROR
    else:
        cm_value, cm_status = None, UNKNOWN
    metrics["contribution_margin"] = metric(cm_value, cm_status, unit)
    if cm_status != OK:
        dep_paths = [p for p, s in (
            (f"mode_a.per_component.{cid}.gross_profit", gp_status),
            (f"mode_a.per_component.{cid}.variable_cost_total", variable_status),
        ) if s != OK]
        code = "DOWNSTREAM_ERROR" if cm_status == ERROR else "DOWNSTREAM_UNKNOWN"
        warnings.append(warn(
            code, "blocking",
            f"mode_a.per_component.{cid}.contribution_margin", dep_paths,
            "gross_profit 또는 variable_cost_total이 UNKNOWN 또는 ERROR라 contribution_margin을 "
            "계산할 수 없습니다.",
        ))

    if cm_status == OK and ex_vat_status == OK and ex_vat_value != 0:
        cmr_value, cmr_status, cmr_code, cmr_message = cm_value / ex_vat_value, OK, None, None
    elif cm_status == ERROR or ex_vat_status == ERROR:
        cmr_value, cmr_status = None, ERROR
        cmr_code = "DOWNSTREAM_ERROR"
        cmr_message = "contribution_margin 또는 actual_price_ex_vat이 ERROR라 비율을 계산할 수 없습니다."
    elif cm_status == OK and ex_vat_status == OK:
        cmr_value, cmr_status = None, ERROR
        cmr_code = "CALCULATION_ERROR"
        cmr_message = "actual_price_ex_vat이 0이라 비율을 계산할 수 없습니다."
    else:
        cmr_value, cmr_status = None, UNKNOWN
        cmr_code = "DOWNSTREAM_UNKNOWN"
        cmr_message = "contribution_margin 또는 actual_price_ex_vat이 확정되지 않아 비율을 계산할 수 없습니다."
    metrics["contribution_margin_rate"] = metric(cmr_value, cmr_status, "ratio")
    if cmr_status != OK:
        warnings.append(warn(
            cmr_code, "blocking",
            f"mode_a.per_component.{cid}.contribution_margin_rate",
            [f"mode_a.per_component.{cid}.contribution_margin", f"mode_a.per_component.{cid}.actual_price_ex_vat"],
            cmr_message,
        ))

    return metrics, warnings


def run_mode_a(client_input: dict) -> dict:
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
