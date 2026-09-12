# -*- coding: utf-8 -*-
"""
MODE C Excel Simulator QA driver (mirrors qa_check_mode_b.py's approach for MODE B).

For each scenario: write the scenario's inputs into a fresh copy of 06_MODE_C_SIMULATOR's live
input cells, force a LibreOffice recalculation, read the recalculated RESULT cells back, and
compare against core/engine/modes/mode_c.py run on the equivalent Client Input. Also sweeps every
recalculated cell in every scenario for a raw Excel error value (#DIV/0!, #VALUE!, #N/A, #NAME?,
#REF!, #NULL!, #NUM!) — none may ever appear (UNKNOWN/ERROR must show as readable text, never a
raw Excel error).

Scenarios mirror docs/features/mode_c_allowable_cost/CASE.md TC1-20 exactly (same numbers as
07_MODE_C_PARITY_TEST in build_workbook.py). TC14/TC15/TC18 exercise the "Variable Cost
Allocation Status" flag; TC19/TC20 exercise the SEPARATE "Direct Cost Allocation Status" flag —
TC19/TC20 are the most important dependency-isolation checks: changing Direct Cost Allocation
Status must never move allowable_direct_cost / expected_contribution_margin(_rate).

Also compares module-status TIER: Python's run_mode_c(ci)["status"] (canonical 3-tier — OK /
INCOMPLETE / ERROR, dependency_rules.md section 5) against 06_MODE_C_SIMULATOR's "Overall
Status" cell, normalized (by string prefix — the cell also carries a human-readable suffix) to
the same 3-tier vocabulary before comparing.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from core.engine.modes.mode_c import run_mode_c  # noqa: E402
from scenario_helpers import make_client_input_c, METRIC_KEYS_C  # noqa: E402

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
BASE_WB = HERE / "Pricing_Harness_Excel_Simulator_v0.5.xlsx"
SCRATCH = HERE / "_qa_scratch_mode_c"

_label_to_row = {}
_wb_for_rows = openpyxl.load_workbook(BASE_WB, read_only=True)
_ws_for_rows = _wb_for_rows["06_MODE_C_SIMULATOR"]
for _row in _ws_for_rows.iter_rows(min_row=1, max_row=40, max_col=2):
    _cell = _row[1]
    if _cell.value and _cell.value not in _label_to_row:
        _label_to_row[_cell.value] = _cell.row
_wb_for_rows.close()

ROW_TARGET_MARKET_PRICE = _label_to_row["Target Market Price"]
ROW_INCLUDES_VAT_C = _label_to_row["Price Includes VAT"]
ROW_VAT_RATE_C = _label_to_row["VAT Rate (v)"]
ROW_TARGET_CM_C = _label_to_row["Target Contribution Margin Rate (t)"]
ROW_FIXED_VAR_C = _label_to_row["Fixed-Amount Variable Cost (F)"]
ROW_NET_SALES_FEE_C = _label_to_row["Net-Sales Fee Rate (b)"]
ROW_GROSS_PAYMENT_FEE_C = _label_to_row["Gross-Payment Fee Rate (a)"]
ROW_ACTUAL_DIRECT_C = _label_to_row["Actual Direct Cost"]
ROW_VCS = _label_to_row["Variable Cost Allocation Status (Excel simulation control — not a schema field)"]
ROW_DCS = _label_to_row["Direct Cost Allocation Status (Excel simulation control — not a schema field)"]

ROW_MARKET_N = _label_to_row["Market Net Sales ex VAT (N)"]
ROW_MARKET_G = _label_to_row["Market Gross Payment incl VAT (G)"]
ROW_ADC = _label_to_row["Allowable Direct Cost (ADC)"]
ROW_ACTUAL_RESULT = _label_to_row["Actual Direct Cost"]  # NOTE: same label reused for input row
ROW_GAP = _label_to_row["Direct Cost Gap (ADC − Actual)"]
ROW_EXPECTED_CM = _label_to_row["Expected Contribution Margin"]
ROW_EXPECTED_CM_RATE = _label_to_row["Expected CM Rate"]
ROW_OVERALL_STATUS = _label_to_row["Overall Status"]

# "Actual Direct Cost" is deliberately used as both the INPUT label and (as
# METRIC_LABELS_C["actual_direct_cost"]) the RESULT label on 06_MODE_C_SIMULATOR — the
# first-match dict built above only captures the INPUT row. Re-scan for the SECOND occurrence
# of "Actual Direct Cost" to get the RESULT row.
_wb2 = openpyxl.load_workbook(BASE_WB, read_only=True)
_ws2 = _wb2["06_MODE_C_SIMULATOR"]
_actual_rows = [row[1].row for row in _ws2.iter_rows(min_row=1, max_row=40, max_col=2) if row[1].value == "Actual Direct Cost"]
_wb2.close()
if len(_actual_rows) >= 2:
    ROW_ACTUAL_RESULT = _actual_rows[1]
else:
    raise RuntimeError("Expected two 'Actual Direct Cost' rows (input + result) on 06_MODE_C_SIMULATOR")

RESULT_ROWS = {
    "market_net_sales_ex_vat": ROW_MARKET_N,
    "market_gross_payment_incl_vat": ROW_MARKET_G,
    "allowable_direct_cost": ROW_ADC,
    "actual_direct_cost": ROW_ACTUAL_RESULT,
    "direct_cost_gap": ROW_GAP,
    "expected_contribution_margin": ROW_EXPECTED_CM,
    "expected_contribution_margin_rate": ROW_EXPECTED_CM_RATE,
}

ERROR_STRINGS = {"#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#REF!", "#NULL!", "#NUM!"}

# Same 20 scenarios (TC1-20) as 07_MODE_C_PARITY_TEST in build_workbook.py.
SCENARIOS = [
    dict(name="TC1. Simple, no fee at all",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC2. Fixed-amount variable cost (F>0)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=5000, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC3. Net-sales fee only (b>0)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0.1, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC4. Gross-payment fee, VAT-exclusive display, v known",
         target_market_price=100000, includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0.05,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC5. VAT-inclusive display, both fee types",
         target_market_price=110000, includes_vat=True, vat_rate=0.10, target_cm_rate=0.3,
         fixed_variable_cost=1000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC6. VAT-exclusive display, same economics as TC5",
         target_market_price=100000, includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
         fixed_variable_cost=1000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC7. VAT-exclusive, v UNKNOWN, a=0 (ADC still OK)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=1000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC8. VAT-exclusive, v UNKNOWN, a>0 (ADC goes UNKNOWN)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0.05,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC9. Target CM rate UNKNOWN",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=None,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC10. Target CM rate invalid (t>=1)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=1.0,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC11. Negative allowable direct cost (valid, warning only)",
         target_market_price=10000, includes_vat=False, vat_rate=0.10, target_cm_rate=0.5,
         fixed_variable_cost=0, net_sales_fee_rate=0.3, gross_payment_fee_rate=0.3,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC12. Actual direct cost below allowable (gap > 0)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=50000, vcs="none", dcs="none"),
    dict(name="TC13. Actual direct cost above allowable (gap < 0)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=90000, vcs="none", dcs="none"),
    dict(name="TC14. Unresolved shared cost (F item) -> ADC UNKNOWN",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="unresolved", dcs="none",
         extra_cost_items=[{
             "item_id": "shared_fixed_var", "label": "공유 고정변동비", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": None, "currency": None, "basis": "per_order",
             "applies_to_component": "shared", "allocation_rule": "by_component_revenue",
         }]),
    dict(name="TC15. Shared + direct invalid configuration -> ADC ERROR",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="invalid", dcs="none",
         extra_cost_items=[{
             "item_id": "shared_net_sales_fee", "label": "모순 설정: shared + direct 수수료",
             "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
             "applies_to_component": "shared", "allocation_rule": "direct",
         }]),
    dict(name="TC16. Explicit zero rate does not block computation",
         target_market_price=100000, includes_vat=False, vat_rate=0.10, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0.05,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC17. No variable-cost items at all (confirmed 0, same as TC1)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC18. Variable-cost item exists but value null -> b UNKNOWN",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=None, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="none"),
    dict(name="TC19. actual_direct_cost UNKNOWN, ADC unaffected (dependency isolation, Case A)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=None, vcs="none", dcs="none"),
    dict(name="TC20. Shared actual_direct_cost unresolved, ADC unaffected (dependency isolation, Case B)",
         target_market_price=100000, includes_vat=False, vat_rate=None, target_cm_rate=0.3,
         fixed_variable_cost=0, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         actual_direct_cost=0, vcs="none", dcs="unresolved",
         extra_cost_items=[{
             "item_id": "shared_actual_direct", "label": "공유 실제직접원가", "cost_category": "product_service_direct_cost",
             "amount": None, "rate": None, "currency": None, "basis": "per_unit",
             "applies_to_component": "shared", "allocation_rule": "by_component_revenue",
         }]),
]

TOL_AMOUNT = 0.01
TOL_RATE = 0.0001
RATE_METRICS = {"expected_contribution_margin_rate"}

EXCEL_STATUS_TO_TIER_PREFIX = [("ERROR", "ERROR"), ("INCOMPLETE", "INCOMPLETE"), ("OK", "OK")]


def _excel_overall_status_tier(text):
    for prefix, tier in EXCEL_STATUS_TO_TIER_PREFIX:
        if text.startswith(prefix):
            return tier
    return f"UNRECOGNIZED({text})"


def run_scenario(scenario):
    name = scenario["name"]
    params = {k: v for k, v in scenario.items() if k not in ("name", "extra_cost_items")}

    wb = openpyxl.load_workbook(BASE_WB)
    ws = wb["06_MODE_C_SIMULATOR"]

    def set_cell(row, value):
        cell = ws.cell(row=row, column=3)
        cell.value = value

    set_cell(ROW_TARGET_MARKET_PRICE, params["target_market_price"])
    set_cell(ROW_INCLUDES_VAT_C, params["includes_vat"])
    set_cell(ROW_VAT_RATE_C, params["vat_rate"])
    set_cell(ROW_TARGET_CM_C, params["target_cm_rate"])
    set_cell(ROW_FIXED_VAR_C, params["fixed_variable_cost"])
    set_cell(ROW_NET_SALES_FEE_C, params["net_sales_fee_rate"])
    set_cell(ROW_GROSS_PAYMENT_FEE_C, params["gross_payment_fee_rate"])
    set_cell(ROW_ACTUAL_DIRECT_C, params["actual_direct_cost"])
    set_cell(ROW_VCS, params["vcs"])
    set_cell(ROW_DCS, params["dcs"])

    safe_name = "".join(ch if ch.isalnum() else "_" for ch in name)[:40]
    scratch_file = SCRATCH / f"{safe_name}.xlsx"
    wb.save(scratch_file)

    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "xlsx", "--outdir", str(SCRATCH / "recalced"), str(scratch_file)],
        check=True, capture_output=True,
    )
    recalced_path = SCRATCH / "recalced" / scratch_file.name
    rwb = openpyxl.load_workbook(recalced_path, data_only=True)
    rws = rwb["06_MODE_C_SIMULATOR"]

    errors_found = []
    for sheet in rwb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value in ERROR_STRINGS:
                    errors_found.append(f"{sheet.title}!{cell.coordinate}={cell.value}")

    excel_results = {mk: rws.cell(row=RESULT_ROWS[mk], column=3).value for mk in METRIC_KEYS_C}
    excel_overall_status_raw = rws.cell(row=ROW_OVERALL_STATUS, column=3).value
    excel_overall_tier = _excel_overall_status_tier(excel_overall_status_raw or "")

    ci_kwargs = {k: v for k, v in scenario.items() if k not in ("name", "vcs", "dcs", "extra_cost_items")}
    ci_kwargs["extra_cost_items"] = scenario.get("extra_cost_items")
    ci = make_client_input_c(**ci_kwargs)
    py_result = run_mode_c(ci)
    py_m = py_result["per_component"]["main"]
    py_results = {mk: (py_m[mk]["value"] if py_m[mk]["status"] == "OK" else py_m[mk]["status"]) for mk in METRIC_KEYS_C}
    py_overall_tier = py_result["status"]

    mismatches = []
    for mk in METRIC_KEYS_C:
        ev = excel_results[mk]
        pv = py_results[mk]
        tol = TOL_RATE if mk in RATE_METRICS else TOL_AMOUNT
        if isinstance(pv, (int, float)):
            if not isinstance(ev, (int, float)) or abs(ev - pv) > tol:
                mismatches.append(f"{mk}: excel={ev!r} python={pv!r}")
        else:
            if ev != pv:
                mismatches.append(f"{mk}: excel={ev!r} python={pv!r}")

    if py_overall_tier != excel_overall_tier:
        mismatches.append(
            f"OVERALL STATUS TIER: excel={excel_overall_tier!r} (raw={excel_overall_status_raw!r}) "
            f"python={py_overall_tier!r}"
        )

    return name, mismatches, errors_found


def main():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    (SCRATCH / "recalced").mkdir(parents=True)

    total_fail = 0
    total_raw_errors = 0
    for scenario in SCENARIOS:
        name, mismatches, errors_found = run_scenario(scenario)
        status = "PASS" if not mismatches and not errors_found else "FAIL"
        print(f"[{status}] {name}")
        if mismatches:
            total_fail += 1
            for m in mismatches:
                print(f"    MISMATCH: {m}")
        if errors_found:
            total_raw_errors += len(errors_found)
            for e in errors_found:
                print(f"    RAW EXCEL ERROR: {e}")

    print()
    print(f"Scenarios: {len(SCENARIOS)}, Failed: {total_fail}, Raw Excel errors found: {total_raw_errors}")
    if total_fail == 0 and total_raw_errors == 0:
        print("MODE C QA: ALL PASS")
        return 0
    print("MODE C QA: FAILURES PRESENT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
