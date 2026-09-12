# -*- coding: utf-8 -*-
"""
Generates the representative Scenario Compare request/result example pair under
core/schemas/examples/scenario_compare/ — baseline + price increase + direct cost reduction
(3 scenarios), matching docs/features/scenario_compare/CASE.md TC1/TC2/TC4's numbers.

Run again after any Scenario Compare engine change and diff the output (same pattern as
core/engine/generate_analysis_results.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.engine.scenario_compare import run_scenario_compare  # noqa: E402
from core.engine.validation.validate_scenario_compare import (  # noqa: E402
    validate_scenario_compare_request,
    validate_scenario_compare_result,
)

OUT_DIR = ROOT / "core" / "schemas" / "examples" / "scenario_compare"

BASE_INPUT = {
    "schema_version": "1.1",
    "client_id": "sample_co_theta",
    "case_id": "sample_case_theta_scenario_compare_001",
    "product": {
        "name": "샘플 정기배송 박스",
        "pricing_model": "one_time",
        "price_components": [
            {
                "component_id": "main", "type": "one_time", "actual_price": 1000,
                "target_market_price": 1000, "currency": "KRW",
                "price_includes_vat": False, "discount_rate": 0,
            }
        ],
    },
    "tax": {"vat_rate": 0.10},
    "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
    "costs": {
        "items": [
            {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
             "amount": 400, "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "var_fixed", "label": "변동비", "cost_category": "variable_selling_delivery",
             "amount": 100, "rate": None, "currency": "KRW", "basis": "per_order", "applies_to_component": "main"},
            {"item_id": "var_net_sales", "label": "매출액기준 변동비", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0, "currency": None, "basis": "rate_of_net_sales", "applies_to_component": "main"},
            {"item_id": "var_gross_payment", "label": "결제액기준 변동비", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0, "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "main"},
            {"item_id": "fixed_ops", "label": "고정운영비", "cost_category": "fixed_operating_cost",
             "amount": 50000, "rate": None, "currency": "KRW", "basis": "per_month", "applies_to_component": "main"},
        ]
    },
    "targets": {"target_contribution_margin_rate": 0.3},
    "meta": {
        "entered_by": "sample", "entered_at": "2026-09-12",
        "notes": "교육용 샘플 데이터 — 실제 기업 데이터 아님. Scenario Compare의 최소 대표 케이스"
                 "(CASE.md TC1/TC2/TC4): baseline, price increase, direct cost reduction.",
    },
}

REQUEST = {
    "base_input": BASE_INPUT,
    "baseline_scenario_id": "A_baseline",
    "scenarios": [
        {"scenario_id": "A_baseline", "label": "현재 가격 유지"},
        {
            "scenario_id": "B_price_up", "label": "가격 인상 (1000 -> 1200)",
            "overrides": {"components": [{"component_id": "main", "actual_price": 1200}]},
        },
        {
            "scenario_id": "D_cost_down", "label": "직접원가 절감 (400 -> 300)",
            "overrides": {"cost_items": [{"item_id": "direct", "amount": 300}]},
        },
    ],
}


def main():
    request_errors = validate_scenario_compare_request(REQUEST)
    if request_errors:
        print("REQUEST SCHEMA FAIL:")
        for e in request_errors:
            print(" ", e)
        sys.exit(1)
    print("REQUEST SCHEMA_PASS")

    result = run_scenario_compare(REQUEST)

    result_errors = validate_scenario_compare_result(result)
    if result_errors:
        print("RESULT SCHEMA FAIL:")
        for e in result_errors:
            print(" ", e)
        sys.exit(1)
    print("RESULT SCHEMA_PASS")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "01_baseline_price_up_cost_down.request.json").write_text(
        json.dumps(REQUEST, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT_DIR / "01_baseline_price_up_cost_down.result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("status:", result["status"])
    for s in result["scenarios"]:
        cm = s["summary"]["per_component"]["main"]["mode_a"]["contribution_margin"]["value"] if "summary" in s else None
        print(f"  {s['scenario_id']}: scenario_status={s['scenario_status']} contribution_margin={cm}")
    print("SAVED:", OUT_DIR)


if __name__ == "__main__":
    main()
