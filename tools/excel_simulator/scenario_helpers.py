# -*- coding: utf-8 -*-
"""
Shared between build_workbook.py and qa_check.py so the Python-side reference
scenarios used to build 03_PARITY_TEST and the ones used to QA-check 01_SIMULATOR
are constructed by the exact same code — not two hand-maintained copies that could
silently drift apart.
"""


def make_client_input(actual_price, includes_vat, vat_rate, direct_cost,
                       channel_fee_rate, pg_fee_rate, delivery, other_var,
                       currency="KRW"):
    items = [
        {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
         "amount": direct_cost, "rate": None, "currency": currency, "basis": "per_unit",
         "applies_to_component": "main"},
        {"item_id": "channel_fee", "label": "채널수수료", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": channel_fee_rate, "currency": None, "basis": "rate_of_net_sales",
         "applies_to_component": "main"},
        {"item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": pg_fee_rate, "currency": None, "basis": "rate_of_gross_payment",
         "applies_to_component": "main"},
        {"item_id": "delivery", "label": "배송/설치비", "cost_category": "variable_selling_delivery",
         "amount": delivery, "rate": None, "currency": currency, "basis": "per_order",
         "applies_to_component": "main"},
        {"item_id": "other_var", "label": "기타변동비", "cost_category": "variable_selling_delivery",
         "amount": other_var, "rate": None, "currency": currency, "basis": "per_order",
         "applies_to_component": "main"},
    ]
    return {
        "schema_version": "1.1", "client_id": "excel_qa", "case_id": "excel_qa_case",
        "product": {"name": "qa", "pricing_model": "one_time", "price_components": [
            {"component_id": "main", "type": "one_time", "actual_price": actual_price,
             "currency": currency, "price_includes_vat": includes_vat}
        ]},
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": currency, "reporting_currency": currency, "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": None},
        "meta": {},
    }


METRIC_KEYS = [
    "actual_price_ex_vat", "direct_cost_total", "gross_profit", "gross_profit_rate",
    "variable_cost_total", "contribution_margin", "contribution_margin_rate",
]

METRIC_LABELS = {
    "actual_price_ex_vat": "Actual Price ex VAT",
    "direct_cost_total": "Direct Cost Total",
    "gross_profit": "Gross Profit",
    "gross_profit_rate": "Gross Profit Rate",
    "variable_cost_total": "Variable Cost Total",
    "contribution_margin": "Contribution Margin",
    "contribution_margin_rate": "Contribution Margin Rate",
}


def make_client_input_b(target_cm_rate, direct_cost, net_sales_fee_rate, gross_payment_fee_rate,
                         vat_rate, includes_vat, discount_rate=None, currency="KRW",
                         extra_cost_items=None):
    """MODE B Client Input builder — single component, flat C/b/a inputs (mirrors how the
    01_SIMULATOR / MODE A builder above keeps a single already-summed rate per category rather
    than an itemized cost list; MODE B's Excel Simulator follows the same simplification).
    See docs/features/mode_b_target_price/SPEC.md and core/engine/modes/mode_b.py.
    `extra_cost_items` lets parity scenarios add shared-cost items (Python-only reference
    scenarios — the Excel Simulator does not implement shared-cost allocation, see SPEC.md §9).
    """
    items = [{
        "item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
        "amount": direct_cost, "rate": None, "currency": currency, "basis": "per_unit",
        "applies_to_component": "main",
    }]
    if net_sales_fee_rate is not None:
        items.append({
            "item_id": "channel_fee", "label": "채널수수료", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": net_sales_fee_rate, "currency": None, "basis": "rate_of_net_sales",
            "applies_to_component": "main",
        })
    if gross_payment_fee_rate is not None:
        items.append({
            "item_id": "pg_fee", "label": "PG수수료", "cost_category": "variable_selling_delivery",
            "amount": None, "rate": gross_payment_fee_rate, "currency": None, "basis": "rate_of_gross_payment",
            "applies_to_component": "main",
        })
    if extra_cost_items:
        items.extend(extra_cost_items)

    return {
        "schema_version": "1.1", "client_id": "excel_qa", "case_id": "excel_qa_case_mode_b",
        "product": {"name": "qa_mode_b", "pricing_model": "one_time", "price_components": [
            {"component_id": "main", "type": "one_time", "actual_price": 1,
             "currency": currency, "price_includes_vat": includes_vat,
             "discount_rate": discount_rate}
        ]},
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": currency, "reporting_currency": currency, "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": target_cm_rate},
        "meta": {},
    }


METRIC_KEYS_B = [
    "denominator", "required_net_sales_ex_vat", "required_gross_payment_incl_vat",
    "required_selling_price", "required_list_price", "expected_contribution_margin",
    "expected_contribution_margin_rate",
]

METRIC_LABELS_B = {
    "denominator": "Denominator",
    "required_net_sales_ex_vat": "Required Net Sales ex VAT",
    "required_gross_payment_incl_vat": "Required Gross Payment incl VAT",
    "required_selling_price": "Required Selling Price",
    "required_list_price": "Required List Price",
    "expected_contribution_margin": "Expected Contribution Margin",
    "expected_contribution_margin_rate": "Expected CM Rate",
}


def make_client_input_c(target_market_price, includes_vat, vat_rate, target_cm_rate,
                         fixed_variable_cost, net_sales_fee_rate, gross_payment_fee_rate,
                         actual_direct_cost, currency="KRW", extra_cost_items=None):
    """MODE C Client Input builder — single component, flat F/b/a + actual_direct_cost inputs
    (mirrors make_client_input_b's simplification: an already-summed rate/amount per category,
    not an itemized cost list). Every flat field is backed by an item that ALWAYS exists (amount/
    rate = the given value, which may be None) so that a blank Excel input and a None Python
    value both mean "item present, value missing" -> UNKNOWN, never "no item at all" -> confirmed
    0 -- see docs/features/mode_c_allowable_cost/SPEC.md section 5's no-item-vs-null table and
    CASE.md TC17 vs TC18/TC19. `extra_cost_items` lets parity scenarios add shared-cost items
    (Python-only reference scenarios -- the Excel Simulator does not implement shared-cost
    allocation, it only proves UNKNOWN/ERROR propagation via the two Allocation Status flags).
    """
    items = [
        {"item_id": "fixed_var", "label": "고정 변동비(F)", "cost_category": "variable_selling_delivery",
         "amount": fixed_variable_cost, "rate": None, "currency": currency, "basis": "per_order",
         "applies_to_component": "main"},
        {"item_id": "net_sales_fee", "label": "매출액 기준 수수료(b)", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": net_sales_fee_rate, "currency": None, "basis": "rate_of_net_sales",
         "applies_to_component": "main"},
        {"item_id": "gross_payment_fee", "label": "결제액 기준 수수료(a)", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": gross_payment_fee_rate, "currency": None, "basis": "rate_of_gross_payment",
         "applies_to_component": "main"},
        {"item_id": "actual_direct", "label": "실제 직접원가", "cost_category": "product_service_direct_cost",
         "amount": actual_direct_cost, "rate": None, "currency": currency, "basis": "per_unit",
         "applies_to_component": "main"},
    ]
    if extra_cost_items:
        items.extend(extra_cost_items)

    return {
        "schema_version": "1.1", "client_id": "excel_qa", "case_id": "excel_qa_case_mode_c",
        "product": {"name": "qa_mode_c", "pricing_model": "one_time", "price_components": [
            {"component_id": "main", "type": "one_time", "actual_price": None,
             "target_market_price": target_market_price,
             "currency": currency, "price_includes_vat": includes_vat}
        ]},
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": currency, "reporting_currency": currency, "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": target_cm_rate},
        "meta": {},
    }


METRIC_KEYS_C = [
    "market_net_sales_ex_vat", "market_gross_payment_incl_vat", "allowable_direct_cost",
    "actual_direct_cost", "direct_cost_gap", "expected_contribution_margin",
    "expected_contribution_margin_rate",
]

METRIC_LABELS_C = {
    "market_net_sales_ex_vat": "Market Net Sales ex VAT (N)",
    "market_gross_payment_incl_vat": "Market Gross Payment incl VAT (G)",
    "allowable_direct_cost": "Allowable Direct Cost (ADC)",
    "actual_direct_cost": "Actual Direct Cost",
    "direct_cost_gap": "Direct Cost Gap (ADC − Actual)",
    "expected_contribution_margin": "Expected Contribution Margin",
    "expected_contribution_margin_rate": "Expected CM Rate",
}


def make_client_input_bep(actual_price, includes_vat, vat_rate, direct_cost,
                           variable_fixed_cost, net_sales_fee_rate, gross_payment_fee_rate,
                           fixed_operating_cost, fixed_operating_cost_basis="per_month",
                           currency="KRW", extra_cost_items=None, extra_components=None):
    """BEP Client Input builder — single component (unless extra_components given, used only by
    the multi-component-gate parity scenarios), flat direct/variable/fixed-cost inputs (mirrors
    tests/test_bep.py's make_input and the same flat-input simplification MODE B/C's Excel
    builders already use). Every flat field is backed by an item that ALWAYS exists (amount/
    rate = the given value, which may be None) so blank Excel input <-> Python "item present,
    value missing" -> UNKNOWN, matching every other mode's Excel builder in this file.
    `fixed_operating_cost=None` means "item exists, amount blank" (UNKNOWN) — to express BEP's
    genuinely different "no fixed-cost item at all" (confirmed 0) case, omit the fc item instead
    via `extra_cost_items`/a custom items list built outside this helper (see qa_check_bep.py's
    "no FC item" scenario, which does not use this default fc-item-always-present shape).

    `net_sales_fee_rate`/`gross_payment_fee_rate` are OMITTED as items entirely when exactly 0
    (rather than included with rate=0), matching tests/test_bep.py's actual scenario construction
    — core/engine/economics.py's sum_cost_category() (shared by MODE A and BEP, unchanged this
    phase) requires a rate item's revenue/gross-payment BASE to be resolvable whenever that item
    is present at all, even at rate=0 (it does not special-case "rate is exactly zero, so the
    base doesn't actually matter" the way mode_b.py/mode_c.py's own bespoke a=0 short-circuits
    do). Omitting a genuinely-zero rate item avoids spuriously requiring `tax.vat_rate` in cases
    like CASE.md TC11 ("a=0, v not needed") — the omitted item and an included rate=0 item are
    numerically equivalent (both contribute 0) whenever the base IS resolvable, so this changes
    no test's actual assertion, only which UNKNOWN-vs-OK path a=0-with-unknown-v takes.
    """
    items = [
        {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
         "amount": direct_cost, "rate": None, "currency": currency, "basis": "per_unit",
         "applies_to_component": "main"},
        {"item_id": "var_fixed", "label": "변동비(금액)", "cost_category": "variable_selling_delivery",
         "amount": variable_fixed_cost, "rate": None, "currency": currency, "basis": "per_order",
         "applies_to_component": "main"},
    ]
    if net_sales_fee_rate:
        items.append({"item_id": "var_net_sales", "label": "매출액 기준 변동비", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": net_sales_fee_rate, "currency": None, "basis": "rate_of_net_sales",
         "applies_to_component": "main"})
    elif net_sales_fee_rate is None:
        items.append({"item_id": "var_net_sales", "label": "매출액 기준 변동비", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": None, "currency": None, "basis": "rate_of_net_sales",
         "applies_to_component": "main"})
    if gross_payment_fee_rate:
        items.append({"item_id": "var_gross_payment", "label": "결제액 기준 변동비", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": gross_payment_fee_rate, "currency": None, "basis": "rate_of_gross_payment",
         "applies_to_component": "main"})
    elif gross_payment_fee_rate is None:
        items.append({"item_id": "var_gross_payment", "label": "결제액 기준 변동비", "cost_category": "variable_selling_delivery",
         "amount": None, "rate": None, "currency": None, "basis": "rate_of_gross_payment",
         "applies_to_component": "main"})
    if fixed_operating_cost is not False:
        items.append({
            "item_id": "fixed_ops", "label": "고정운영비", "cost_category": "fixed_operating_cost",
            "amount": fixed_operating_cost, "rate": None, "currency": currency,
            "basis": fixed_operating_cost_basis, "applies_to_component": "main",
        })
    if extra_cost_items:
        items.extend(extra_cost_items)

    components = [{
        "component_id": "main", "type": "one_time", "actual_price": actual_price,
        "currency": currency, "price_includes_vat": includes_vat,
    }]
    if extra_components:
        components.extend(extra_components)

    return {
        "schema_version": "1.1", "client_id": "excel_qa", "case_id": "excel_qa_case_bep",
        "product": {"name": "qa_bep", "pricing_model": "one_time", "price_components": components},
        "tax": {"vat_rate": vat_rate},
        "fx": {"base_currency": currency, "reporting_currency": currency, "rate_base_per_reporting": 1},
        "costs": {"items": items},
        "targets": {"target_contribution_margin_rate": None},
        "meta": {},
    }


METRIC_KEYS_BEP = [
    "contribution_margin_per_unit", "fixed_operating_cost", "break_even_quantity_exact",
]

METRIC_LABELS_BEP = {
    "contribution_margin_per_unit": "Contribution Margin per Unit (CMu)",
    "fixed_operating_cost": "Fixed Operating Cost (FC)",
    "break_even_quantity_exact": "Break-Even Quantity (Q_BEP)",
}
