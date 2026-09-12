# -*- coding: utf-8 -*-
"""
Shared primitives for MODE A/B (and future modules) — see core/schemas/dependency_rules.md.

Deliberately minimal. This is NOT a generic dependency-resolution framework and does NOT
include a cost-aggregation helper — each mode's cost aggregation has different consumption
shapes (MODE A sums into one total per category; MODE B needs three separate coefficients) and
generalizing that before a third mode exists would be guessing at the wrong abstraction.
"""
from __future__ import annotations

OK = "OK"
UNKNOWN = "UNKNOWN"
ERROR = "ERROR"


def metric(value, status, unit):
    return {"value": value, "status": status, "unit": unit}


def warn(code, severity, metric_path, dependency_paths, message):
    return {
        "code": code,
        "severity": severity,
        "metric_path": metric_path,
        "dependency_paths": list(dependency_paths),
        "message": message,
    }


def convert_to_reporting(amount, item_currency, fx):
    """(value, status, dependency_path_or_None). Supports same-currency and
    base_currency->reporting_currency via fx.rate_base_per_reporting only."""
    reporting = fx["reporting_currency"]
    base = fx["base_currency"]
    if item_currency == reporting:
        return amount, OK, None
    if item_currency == base:
        rate = fx.get("rate_base_per_reporting")
        if rate is None:
            return None, UNKNOWN, "fx.rate_base_per_reporting"
        return amount / rate, OK, None
    return None, ERROR, f"<unsupported currency '{item_currency}' for reporting '{reporting}'>"


def aggregate_module_status(metrics):
    """Canonical 3-tier module status (dependency_rules.md section 5, revised): ERROR takes
    priority over UNKNOWN — a module is ERROR if any metric is ERROR, else INCOMPLETE if any
    metric is UNKNOWN, else OK. `metrics` is an iterable of {value,status,unit} dicts pooled
    across every component the module computed (module status is not per-component)."""
    statuses = [m["status"] for m in metrics]
    if any(s == ERROR for s in statuses):
        return ERROR
    if any(s == UNKNOWN for s in statuses):
        return "INCOMPLETE"
    return OK


def resolve_price_basis(price, price_includes_vat, vat_rate, component_id):
    """Forward price-basis normalization: given an already-currency-converted raw price and the
    component's price_includes_vat / tax.vat_rate, derive (net_sales_ex_vat, gross_payment_incl_vat)
    — each returned as (value, status, dependency_paths), the same shape every metric in this
    Harness uses. This is the *forward* direction (price -> N, G); it does not decide which of
    N/G is the "headline" price for a mode that instead needs to invert the relationship (e.g.
    MODE B solving for a target price) — that selection logic stays local to that mode.

    Rule (dependency_rules.md section 2 — unchanged by this extraction, only relocated):
    price_includes_vat = null  -> both N and G UNKNOWN (don't even know which one `price` is).
    price_includes_vat = true  -> G = price (OK, rate irrelevant here); N = price/(1+v), needs v.
    price_includes_vat = false -> N = price (OK, rate irrelevant here); G = price*(1+v), needs v.
    vat_rate = 0 is a valid, explicit zero (null != 0) and resolves N/G normally, never UNKNOWN.
    """
    incl_dep = [f"product.price_components[{component_id}].price_includes_vat"]
    vat_dep = ["tax.vat_rate"]

    if price_includes_vat is None:
        return (None, UNKNOWN, incl_dep), (None, UNKNOWN, incl_dep)

    if price_includes_vat is False:
        n = (price, OK, [])
        if vat_rate is None:
            g = (None, UNKNOWN, vat_dep)
        else:
            g = (price * (1 + vat_rate), OK, [])
        return n, g

    # price_includes_vat is True
    g = (price, OK, [])
    if vat_rate is None:
        n = (None, UNKNOWN, vat_dep)
    else:
        n = (price / (1 + vat_rate), OK, [])
    return n, g
