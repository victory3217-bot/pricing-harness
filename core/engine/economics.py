# -*- coding: utf-8 -*-
"""
Shared economic aggregation primitives — used by more than one mode (currently MODE A and BEP).

Deliberately narrow: only the price-normalization glue and the generic cost-category
summation loop that MODE A and BEP need *identically*. MODE B's flat C/b/a coefficients and
MODE C's F/b/a-with-ADC/actual-isolation are shaped differently enough that they stay local to
mode_b.py/mode_c.py — this file is not a place to force every mode's cost logic into one shape.
Likewise BEP's own fixed_operating_cost aggregation (core/engine/modes/bep.py's
_sum_fixed_operating_cost) stays BEP-local: its blended_only -> UNKNOWN deviation and
negative-amount/basis-consistency checks are BEP-specific semantics, not shared with anything.

No function here embeds a module-specific metric_path or warning message/code — every function
returns plain (value, status, dependency_paths) data (or a superset shaped the same way); the
caller (mode_a.py's compute_component, bep.py's compute_component) owns building metric_path,
warning code/message, and any module-specific dependency-path prefixing.
"""
from __future__ import annotations

from core.engine.common import ERROR, OK, UNKNOWN, convert_to_reporting

DIRECT = "product_service_direct_cost"
VARIABLE = "variable_selling_delivery"


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
