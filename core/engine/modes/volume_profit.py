# -*- coding: utf-8 -*-
"""
Volume Profit — operating profit and margin of safety at a planned sales quantity.

Pure calculation: a Client Input with a `sales_plan` -> per-component total net sales, total
contribution margin, operating profit, break-even quantity and margin of safety. Formulas, status
rules and decisions follow docs/features/volume_profit/SPEC.md (DRAFT v0.2) exactly — do not
diverge from it without updating that SPEC first.

Question this module answers: "if `planned_quantity` units are sold in the analysis period, what
is left after fixed operating cost, and how far is that plan from break-even?"

Design (SPEC.md section 2/5): takes only `client_input`, like run_mode_a/b/c/bep, and recomputes
CMu and FC itself through core/engine/economics.py — it never reads a mode_a or bep result
object. The per-unit economics are MODE A's; this module adds the quantity and one deliberate
exception, units_per_order (below), so with units_per_order != 1 its CMu differs from MODE A's.

Every metric is judged from four *leaves*, never from another output metric's status:
    Q    planned quantity (+ its period)        owner metric: planned_quantity
    N    net sales ex VAT per unit              owner metric: total_net_sales_ex_vat
    COST direct + variable cost per unit        owner metric: total_contribution_margin
    FC   fixed_operating_cost for the period    owner metric: operating_profit
A leaf's own warning (specific code, raw Client Input dependency paths) is attached to its owner
metric once; any other metric that depends on a non-OK leaf gets a single DOWNSTREAM_* warning
pointing at the owner metric's path. This keeps one root cause from producing eight identical
warnings while still letting every metric explain why it is not OK.

Gate order (SPEC.md section 5): no sales_plan -> NOT_RUN; more than one price component -> ERROR
(MULTI_COMPONENT_VOLUME_PROFIT_NOT_SUPPORTED, per_component {}); only then anything else.

Negative results are meaningful here, unlike BEP: operating_profit and margin_of_safety_quantity
may be negative with status OK/ESTIMATED (a loss / a plan below break-even — BELOW_BREAK_EVEN
warning), never clamped. break_even_quantity_exact keeps BEP's rule exactly (NOT_APPLICABLE for
CMu <= 0, never a raw 0 or negative number).

per_order cost items are paid once per order but multiplied here by a unit count (SPEC.md section
11). sales_plan.units_per_order resolves that: per_order amounts are divided by it, the metrics stay
OK, and an info warning UNITS_PER_ORDER_APPLIED notes that MODE A and BEP still treat per_order
costs as per-unit. When units_per_order is omitted and a per_order item exists, one unit per order is
assumed: every metric that depends on COST is ESTIMATED, with an ASSUMES_ONE_UNIT_PER_ORDER
warning. A value that is not a number > 0 is an ERROR (INVALID_UNITS_PER_ORDER). ESTIMATED does not
lower module status (common.aggregate_module_status only looks at ERROR and UNKNOWN).

Not implemented, by design (SPEC.md section 9): the period-mismatch cross-check between
sales_plan.period_basis and the fixed-cost basis. With per_month the only supported value on both
sides it is unreachable; add it together with the second period.
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
ESTIMATED = "ESTIMATED"
NOT_RUN = "NOT_RUN"

SUPPORTED_PERIOD = "per_month"
PER_ORDER = "per_order"

_BREAK_EVEN_NA_MESSAGES = {
    "BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST":
        "고정비와 단위 마진이 모두 0입니다 — 손익분기 판매량이라는 개념이 정의되지 않습니다 (0/0).",
    "BREAK_EVEN_UNDEFINED_ZERO_MARGIN":
        "현재 단위 마진이 0이라 어떤 판매량으로도 고정비를 회수할 수 없습니다.",
    "BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN":
        "판매할수록 손실이 커지는 구조입니다(단위 마진 음수). 이 가격·비용구조에서는 손익분기 판매량이라는 "
        "개념 자체가 성립하지 않습니다.",
}


def _leaf(status, deps=None, code=None, message=None):
    return {"status": status, "deps": list(deps or []), "code": code, "message": message}


def _quantity_leaf(plan):
    q = plan.get("planned_quantity")
    period = plan.get("period_basis")

    if q is not None and q < 0:
        return _leaf(ERROR, ["sales_plan.planned_quantity"], "INVALID_NEGATIVE_QUANTITY",
                     "계획 판매량이 음수입니다 — 유효한 입력이 아닙니다.")
    if period is not None and period != SUPPORTED_PERIOD:
        return _leaf(ERROR, ["sales_plan.period_basis"], "UNSUPPORTED_PLAN_PERIOD",
                     f"계획 판매량의 기간 기준 '{period}'은(는) 지원하지 않습니다 (v0.1은 {SUPPORTED_PERIOD}만 지원).")

    missing = []
    if q is None:
        missing.append("sales_plan.planned_quantity")
    if period is None:
        missing.append("sales_plan.period_basis")
    if missing:
        return _leaf(UNKNOWN, missing, "MISSING_DEPENDENCY",
                     "계획 판매량 또는 그 기간 기준이 미입력되어 판매량 기반 지표를 계산할 수 없습니다 "
                     "(기간을 임의로 가정하지 않습니다).")
    return {**_leaf(OK), "value": q}


def _units_per_order(plan):
    """(value, error_leaf). value None = not provided: the caller assumes 1 unit per order and
    marks the dependent metrics ESTIMATED (SPEC.md section 11). A provided value that is not a
    number > 0 (including NaN and booleans) is an error leaf instead."""
    u = plan.get("units_per_order")
    if u is None:
        return None, None
    if isinstance(u, bool) or not isinstance(u, (int, float)) or not u > 0:
        return None, _leaf(ERROR, ["sales_plan.units_per_order"], "INVALID_UNITS_PER_ORDER",
                           "주문당 판매 수량(units_per_order)은 0보다 큰 숫자여야 합니다.")
    return u, None


def _net_sales_leaf(client_input, component):
    price_value, price_status, price_deps = price_converted(component, client_input["fx"])
    if price_status != OK:
        n_value, n_status, n_deps = None, price_status, price_deps
        g_value, g_status, g_deps = None, price_status, price_deps
    else:
        (n_value, n_status, n_deps), (g_value, g_status, g_deps) = resolve_price_basis(
            price_value, component.get("price_includes_vat"), client_input["tax"].get("vat_rate"),
            component["component_id"])

    if n_status == OK:
        leaf = {**_leaf(OK), "value": n_value}
    elif n_status == ERROR:
        leaf = _leaf(ERROR, n_deps, "CALCULATION_ERROR", "가격/VAT 관련 필드에 오류가 있어 순매출을 계산할 수 없습니다.")
    else:
        leaf = _leaf(UNKNOWN, n_deps, "MISSING_DEPENDENCY",
                     "판매가 또는 VAT 관련 필드가 미입력되어 VAT 제외 순매출을 계산할 수 없습니다.")
    return leaf, (n_value, n_status, n_deps), (g_value, g_status, g_deps)


def _cost_leaf(client_input, component, revenue_ex_vat, gross_payment, units_per_order=None):
    """UNKNOWN only because net sales (N) is itself not OK is marked `via: "N"` with no code of its
    own: the root cause is already warned on N's owner metric, and a rate-based cost item
    (e.g. a PG fee on gross payment) cannot be computed without a price either.

    `units_per_order` (None = not provided -> 1) divides every per_order amount (SPEC.md section 11)."""
    cid = component["component_id"]
    per_order_units = 1.0 if units_per_order is None else units_per_order
    direct_total, direct_status, direct_deps = sum_cost_category(
        client_input, cid, DIRECT, revenue_ex_vat, gross_payment, per_order_units)
    variable_total, variable_status, variable_deps = sum_cost_category(
        client_input, cid, VARIABLE, revenue_ex_vat, gross_payment, per_order_units)

    error_deps, unknown_deps = [], []
    for status, deps in ((direct_status, direct_deps), (variable_status, variable_deps)):
        if status == ERROR:
            error_deps.extend(deps)
        elif status != OK:
            unknown_deps.extend(deps)

    if error_deps:
        invalid_alloc = any(p.endswith(".allocation_rule") for p in error_deps)
        return _leaf(
            ERROR, error_deps,
            "INVALID_ALLOCATION_CONFIGURATION" if invalid_alloc else "CALCULATION_ERROR",
            "shared 비용에 allocation_rule=direct가 설정되어 있어 단위당 비용을 계산할 수 없습니다."
            if invalid_alloc else "비용 항목에 오류가 있어 단위당 비용을 계산할 수 없습니다.")
    if unknown_deps:
        n_status, n_deps = revenue_ex_vat[1], revenue_ex_vat[2]
        if n_status != OK and set(unknown_deps) <= set(n_deps):
            return {**_leaf(UNKNOWN), "via": "N"}
        return _leaf(UNKNOWN, unknown_deps, "MISSING_DEPENDENCY",
                     "직접원가·변동비 항목이 미입력되었거나 공유비용 배부 규칙이 아직 지원되지 않아 단위당 비용을 "
                     "계산할 수 없습니다.")
    return {**_leaf(OK), "value": direct_total + variable_total}


def _fixed_cost_leaf(client_input, cid):
    fc_value, fc_status, fc_code, fc_deps, period_basis = sum_fixed_operating_cost(client_input, cid)
    if fc_status == OK and period_basis not in (None, SUPPORTED_PERIOD):
        return _leaf(
            ERROR, [], "UNSUPPORTED_FIXED_COST_BASIS_FOR_VOLUME",
            f"고정운영비의 기간 기준 '{period_basis}'은(는) 판매량 기반 손익에서 지원하지 않습니다 "
            f"({SUPPORTED_PERIOD}만 지원)."), period_basis
    if fc_status == OK:
        return {**_leaf(OK), "value": fc_value}, period_basis
    return _leaf(fc_status, fc_deps, fc_code, FIXED_COST_MESSAGES[fc_code]), period_basis


def _has_per_order_cost(client_input, cid):
    return any(
        item["cost_category"] in (DIRECT, VARIABLE)
        and item["applies_to_component"] == cid
        and item["basis"] == PER_ORDER
        and item.get("amount") is not None
        for item in client_input["costs"]["items"]
    )


def compute_component(client_input, component, plan):
    cid = component["component_id"]
    unit = client_input["fx"]["reporting_currency"]
    base = f"volume_profit.per_component.{cid}"
    path = {name: f"{base}.{name}" for name in (
        "planned_quantity", "total_net_sales_ex_vat", "total_contribution_margin", "operating_profit",
        "operating_profit_rate", "break_even_quantity_exact", "margin_of_safety_quantity",
        "margin_of_safety_rate")}

    q = _quantity_leaf(plan)
    n, revenue_ex_vat, gross_payment = _net_sales_leaf(client_input, component)
    units, units_error = _units_per_order(plan)
    cost = units_error or _cost_leaf(client_input, component, revenue_ex_vat, gross_payment, units)
    fc, period_basis = _fixed_cost_leaf(client_input, cid)
    leaves = {"Q": q, "N": n, "COST": cost, "FC": fc}
    owner_path = {"Q": path["planned_quantity"], "N": path["total_net_sales_ex_vat"],
                  "COST": path["total_contribution_margin"], "FC": path["operating_profit"]}
    has_per_order = cost["status"] == OK and _has_per_order_cost(client_input, cid)
    assumes_per_order = has_per_order and units is None
    applied_units = has_per_order and units is not None and units != 1

    # Leaf values exist only when that leaf is OK; a metric's value_fn runs only when every leaf
    # it depends on is OK, so it never sees a missing value.
    Q, N, C, F = q.get("value"), n.get("value"), cost.get("value"), fc.get("value")
    cmu = N - C if N is not None and C is not None else None

    metrics = {}
    warnings = []

    def settle(name, deps_on, mu, *, depends_on_cost, value_fn=None):
        """Status/value/warnings for one metric. `value_fn()` runs only when every leaf in
        `deps_on` is OK and returns (value, na_code_or_None); it is the only place a
        NOT_APPLICABLE can arise."""
        statuses = [leaves[k]["status"] for k in deps_on]
        na_code = None
        if ERROR in statuses:
            status, value = ERROR, None
        elif UNKNOWN in statuses:
            status, value = UNKNOWN, None
        else:
            value, na_code = value_fn()
            if na_code is not None:
                status, value = NOT_APPLICABLE, None
            else:
                status = ESTIMATED if (depends_on_cost and assumes_per_order) else OK
        metrics[name] = metric(value, status, mu)

        if status in (ERROR, UNKNOWN):
            downstream = []
            for k in deps_on:
                leaf = leaves[k]
                if leaf["status"] == OK:
                    continue
                via = leaf.get("via")
                if via is None and owner_path[k] == path[name]:
                    warnings.append(warn(leaf["code"], "blocking", path[name], leaf["deps"], leaf["message"]))
                else:
                    downstream.append(owner_path[via or k])
            if downstream:
                code = "DOWNSTREAM_ERROR" if status == ERROR else "DOWNSTREAM_UNKNOWN"
                warnings.append(warn(code, "blocking", path[name], sorted(set(downstream)),
                                     "상위 입력 또는 지표가 UNKNOWN/ERROR라 계산할 수 없습니다."))
        elif status == NOT_APPLICABLE:
            code = na_code
            message = _BREAK_EVEN_NA_MESSAGES.get(code) or {
                "ZERO_NET_SALES_RATE_UNDEFINED": "총순매출이 0이라 영업이익률을 계산할 수 없습니다.",
                "ZERO_QUANTITY_RATE_UNDEFINED": "계획 판매량이 0이라 안전한계율을 계산할 수 없습니다.",
            }[code]
            warnings.append(warn(code, "warning", path[name], [], message))
        return status, value

    # --- planned_quantity (owner of Q's warning) ---
    settle("planned_quantity", ["Q"], "units", depends_on_cost=False, value_fn=lambda: (Q, None))

    # --- total_net_sales_ex_vat = N x Q (owner of N's warning) ---
    settle("total_net_sales_ex_vat", ["Q", "N"], unit, depends_on_cost=False,
           value_fn=lambda: (N * Q, None))

    # --- total_contribution_margin = CMu x Q (owner of COST's warning) ---
    settle("total_contribution_margin", ["Q", "N", "COST"], unit, depends_on_cost=True,
           value_fn=lambda: (cmu * Q, None))

    # --- operating_profit = CMu x Q - FC (owner of FC's warning); may be negative ---
    settle("operating_profit", ["Q", "N", "COST", "FC"], unit, depends_on_cost=True,
           value_fn=lambda: (cmu * Q - F, None))

    # --- operating_profit_rate = operating_profit / total_net_sales ---
    def operating_profit_rate():
        if N * Q == 0:
            return None, "ZERO_NET_SALES_RATE_UNDEFINED"
        return (cmu * Q - F) / (N * Q), None

    settle("operating_profit_rate", ["Q", "N", "COST", "FC"], "ratio", depends_on_cost=True,
           value_fn=operating_profit_rate)

    # --- break_even_quantity_exact = FC / CMu — BEP's rules exactly (bep/SPEC.md section 6/9);
    #     does not need Q, so it is judged on N/COST/FC only ---
    def break_even_quantity():
        if cmu == 0:
            return None, ("BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST" if F == 0
                          else "BREAK_EVEN_UNDEFINED_ZERO_MARGIN")
        if cmu < 0:
            return None, "BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN"
        return F / cmu, None

    be_status, be_value = settle("break_even_quantity_exact", ["N", "COST", "FC"], "units",
                                 depends_on_cost=True, value_fn=break_even_quantity)
    be_na_code = None
    if be_status == NOT_APPLICABLE:
        be_na_code = break_even_quantity()[1]

    # --- margin_of_safety_quantity = Q - Q_BEP; negative is a meaningful OK answer ---
    mos_status, mos_value = settle(
        "margin_of_safety_quantity", ["Q", "N", "COST", "FC"], "units", depends_on_cost=True,
        value_fn=lambda: (None, be_na_code) if be_status == NOT_APPLICABLE else (Q - be_value, None))
    if mos_status in (OK, ESTIMATED) and mos_value < 0:
        warnings.append(warn(
            "BELOW_BREAK_EVEN", "warning", path["margin_of_safety_quantity"], [],
            "계획 판매량이 손익분기 판매량에 못 미칩니다 — 고정운영비를 회수하지 못합니다."))

    # --- margin_of_safety_rate = (Q - Q_BEP) / Q ---
    def margin_of_safety_rate():
        if be_status == NOT_APPLICABLE:
            return None, be_na_code
        if Q == 0:
            return None, "ZERO_QUANTITY_RATE_UNDEFINED"
        return (Q - be_value) / Q, None

    settle("margin_of_safety_rate", ["Q", "N", "COST", "FC"], "ratio", depends_on_cost=True,
           value_fn=margin_of_safety_rate)

    if assumes_per_order and metrics["total_contribution_margin"]["status"] == ESTIMATED:
        warnings.append(warn(
            "ASSUMES_ONE_UNIT_PER_ORDER", "warning", path["total_contribution_margin"], [],
            "per_order 비용을 주문당 1개 판매로 가정했습니다. 주문당 구매 수량이 1개보다 크면 비용이 "
            "과대 계상되고 영업이익이 과소 계상됩니다."))
    if applied_units and metrics["total_contribution_margin"]["status"] == OK:
        warnings.append(warn(
            "UNITS_PER_ORDER_APPLIED", "info", path["total_contribution_margin"], [],
            f"per_order 비용을 주문당 평균 {units:g}개로 나눠 개당 비용으로 환산했습니다. MODE A와 BEP는 "
            "per_order 비용을 개당 비용으로 취급하므로(주문당 1개 가정) 그 결과와 달라질 수 있습니다."))

    return {"analysis_period_basis": period_basis, **metrics}, warnings


def run_volume_profit(client_input: dict) -> dict:
    plan = client_input.get("sales_plan")
    if plan is None:
        return {"status": NOT_RUN, "per_component": {}, "warnings": []}

    components = client_input["product"]["price_components"]
    if len(components) > 1:
        return {
            "status": ERROR,
            "per_component": {},
            "warnings": [warn(
                "MULTI_COMPONENT_VOLUME_PROFIT_NOT_SUPPORTED", "blocking", "volume_profit",
                ["product.price_components"],
                "Volume Profit v0.1은 단일 컴포넌트 상품만 지원합니다 — 이 Client Input은 컴포넌트가 2개 "
                "이상이라 계산하지 않습니다 (shared fixed cost 이중계상 방지).",
            )],
        }

    per_component = {}
    all_warnings = []
    all_metrics = []
    for component in components:
        metrics, warnings = compute_component(client_input, component, plan)
        per_component[component["component_id"]] = metrics
        all_warnings.extend(warnings)
        all_metrics.extend(m for k, m in metrics.items() if k != "analysis_period_basis")

    return {
        "status": aggregate_module_status(all_metrics),
        "per_component": per_component,
        "warnings": all_warnings,
    }
