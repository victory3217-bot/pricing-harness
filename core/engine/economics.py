# -*- coding: utf-8 -*-
"""
Shared economic aggregation primitives — used by more than one mode (MODE A, BEP, Volume Profit).

Deliberately narrow: only the price-normalization glue and the generic cost-category
summation loop that MODE A and BEP need *identically*. MODE B's flat C/b/a coefficients and
MODE C's F/b/a-with-ADC/actual-isolation are shaped differently enough that they stay local to
mode_b.py/mode_c.py — this file is not a place to force every mode's cost logic into one shape.
Fixed-operating-cost aggregation (sum_fixed_operating_cost) also lives here because BEP and
Volume Profit both need it identically; it is deliberately a separate function from sum_cost_category,
not a variant of it, because its blended_only -> UNKNOWN deviation and its negative-amount and
basis-consistency checks are fixed-cost-specific semantics (docs/features/bep/SPEC.md section 12).

No function here embeds a module-specific metric_path — every function returns plain
(value, status, dependency_paths) data (or a superset shaped the same way); the caller owns
building metric_path and any module-specific dependency-path prefixing. FIXED_COST_MESSAGES is
the one shared piece of warning text, keyed by the code sum_fixed_operating_cost returns.
"""
from __future__ import annotations

from core.engine.common import ERROR, OK, UNKNOWN, convert_to_reporting

DIRECT = "product_service_direct_cost"
VARIABLE = "variable_selling_delivery"
FIXED = "fixed_operating_cost"

FIXED_COST_MESSAGES = {
    "INVALID_NEGATIVE_COST": "fixed_operating_cost 항목의 금액이 음수입니다 — 유효한 비용으로 취급하지 않습니다.",
    "INVALID_ALLOCATION_CONFIGURATION": "shared 비용에 allocation_rule=direct가 설정되어 있어 fixed_operating_cost를 계산할 수 없습니다.",
    "UNSUPPORTED_CURRENCY": "fixed_operating_cost 항목의 통화를 reporting currency로 환산할 수 없습니다 (미지원 통화).",
    "INCONSISTENT_FIXED_COST_BASIS": "이 컴포넌트에 귀속되는 fixed_operating_cost 항목들의 basis(분석기간)가 서로 달라 합산할 수 없습니다.",
    "FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED": "fixed_operating_cost 항목이 blended_only로 설정되어 있어(컴포넌트별 배부 대상이 아님) 아직 배부되지 않았습니다 — 0으로 취급하지 않습니다.",
    "UNSUPPORTED_SHARED_COST_ALLOCATION": "fixed_operating_cost 중 shared 비용이 있으나 배부(allocation) 결과가 없어 계산할 수 없습니다 (0으로 취급하지 않음).",
    "MISSING_DEPENDENCY": "fixed_operating_cost 항목이 미입력되어 계산할 수 없습니다.",
}


def price_converted(component, fx, price_field="actual_price"):
    """(value, status, dependency_paths) for component[price_field], in reporting currency.

    Shared by MODE A (price_field="actual_price", the default) and BEP (also "actual_price" —
    BEP's price source is always the current actual price, never a target/market price; see
    docs/features/bep/SPEC.md section 1). MODE B/C key off different fields
    (targets/required_selling_price, price_components[].target_market_price respectively) with
    their own local logic and are not parameterized through this function.
    """
    price = component.get(price_field)
    cid = component["component_id"]
    if price is None:
        return None, UNKNOWN, [f"product.price_components[{cid}].{price_field}"]
    value, status, dep = convert_to_reporting(price, component.get("currency"), fx)
    if status != OK:
        return None, status, [dep]
    return value, OK, []


def sum_cost_category(client_input, component_id, category, revenue_ex_vat, gross_payment):
    """
    Sum every cost item in `category` that applies to `component_id` (directly, or shared
    with a resolvable allocation). Returns (value, status, dependency_paths).

    A category with zero matching items is a confirmed 0 (nothing to sum), not UNKNOWN —
    there is no missing data, just no cost of that kind assigned to this component.

    `revenue_ex_vat` and `gross_payment` are each (value, status, deps) triples — when a
    rate-based item's base isn't OK, the *base's own* dependency paths are what get recorded
    (e.g. `tax.vat_rate`), not the item's `.rate` field, which may itself be perfectly known.

    A shared item with allocation_rule == "direct" is a semantic contradiction (dependency_rules
    section 4) and contributes to `error_deps`, not `deps` — it makes this category ERROR, not
    UNKNOWN, and is never used as-is. This is the DIRECT/VARIABLE-category shared-cost rule only;
    fixed_operating_cost's shared-cost handling (including its blended_only deviation) is
    BEP-local, see core/engine/modes/bep.py.
    """
    fx = client_input["fx"]
    total = 0.0
    deps = []
    error_deps = []
    any_item = False

    for item in client_input["costs"]["items"]:
        if item["cost_category"] != category:
            continue
        applies = item["applies_to_component"]

        if applies == component_id:
            pass
        elif applies == "shared":
            rule = item.get("allocation_rule")
            if rule == "blended_only":
                continue  # by design, never appears at component level
            any_item = True
            if rule == "direct":
                error_deps.append(f"costs.items[{item['item_id']}].allocation_rule")
                continue
            if rule in ("by_component_revenue", "fixed_share"):
                # Resolving this requires the blended (whole-contract) engine, not built yet.
                deps.append(f"blended.allocation[{item['item_id']}]")
                continue
            deps.append(f"costs.items[{item['item_id']}].allocation_rule")
            continue
        else:
            continue

        any_item = True
        amount = item.get("amount")
        rate = item.get("rate")

        if amount is not None:
            value, status, dep = convert_to_reporting(amount, item.get("currency"), fx)
            if status != OK:
                deps.append(dep or f"costs.items[{item['item_id']}].amount")
                continue
            total += value
        elif rate is not None:
            basis = item["basis"]
            if basis == "rate_of_net_sales":
                base_value, base_status, base_deps = revenue_ex_vat
            elif basis == "rate_of_gross_payment":
                base_value, base_status, base_deps = gross_payment
            else:
                deps.append(f"costs.items[{item['item_id']}].basis")
                continue
            if base_status != OK:
                # The rate itself is known — blame the base's real dependency, not the rate.
                deps.extend(base_deps)
                continue
            total += base_value * rate
        else:
            deps.append(f"costs.items[{item['item_id']}].amount")
            deps.append(f"costs.items[{item['item_id']}].rate")

    if not any_item:
        return 0.0, OK, []
    if error_deps:
        return None, ERROR, error_deps
    if deps:
        return None, UNKNOWN, deps
    return total, OK, []


def sum_fixed_operating_cost(client_input, component_id):
    """(value, status, code, dependency_paths, analysis_period_basis).

    Mirrors economics.sum_cost_category's no-item/null/explicit-zero + shared-cost classification
    pattern (see that function's docstring), with fixed-cost-specific additions — kept as a
    separate function from sum_cost_category on purpose (see this module's docstring and
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
