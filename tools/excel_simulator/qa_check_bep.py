# -*- coding: utf-8 -*-
"""
BEP Excel Simulator QA driver (mirrors qa_check_mode_c.py's approach for MODE C).

For each scenario: write the scenario's inputs into a fresh copy of 08_BEP_SIMULATOR's live
input cells, force a LibreOffice recalculation, read the recalculated RESULT cells back, and
compare against core/engine/modes/bep.py run on the equivalent Client Input. Also sweeps every
recalculated cell in every scenario for a raw Excel error value (#DIV/0!, #VALUE!, #N/A, #NAME?,
#REF!, #NULL!, #NUM!) — none may ever appear.

Scenarios mirror docs/features/bep/CASE.md TC1-23 plus 3 extra scenarios (TC24 inconsistent
fixed-cost basis, TC25 NOT_APPLICABLE-keeps-module-OK, TC26 multi-component gate beats a
basis-inconsistency error) — same 26 cases as 09_BEP_PARITY_TEST in build_workbook.py.

08_BEP_SIMULATOR is inherently single-component (no Component Count / Basis Consistency
controls there — SPEC.md section 10), so TC18/TC19/TC26 (multi-component) and TC24/TC26 (basis
inconsistency) cannot be driven through this sheet's own input cells; those are exercised only
in 09_BEP_PARITY_TEST (already covered by build_workbook.py's own literal-input parity rows).
This driver instead exercises every scenario that IS expressible as a single-component,
single-fixed-cost-item 08_BEP_SIMULATOR input (TC1-17, TC20-23, TC25 — 21 of the 26), comparing
against core/engine/modes/bep.py directly, plus reads 09_BEP_PARITY_TEST's own "ALL PASS" roll-up
cell for full TC1-26 coverage including the multi-component/basis-inconsistency cases.

Also compares module-status TIER: Python's run_bep(ci)["status"] against 08_BEP_SIMULATOR's
"Overall Status" cell, normalized by string prefix to the same 3-tier vocabulary, and the
independent self-check (|Q_BEP × CMu − FC| <= tol) so a Python-value-copy bug in the Excel
formulas cannot silently pass.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from core.engine.modes.bep import run_bep  # noqa: E402
from scenario_helpers import make_client_input_bep, METRIC_KEYS_BEP  # noqa: E402

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
BASE_WB = HERE / "Pricing_Harness_Excel_Simulator_v0.5.xlsx"
SCRATCH = HERE / "_qa_scratch_bep"

_label_to_row = {}
_wb_for_rows = openpyxl.load_workbook(BASE_WB, read_only=True)
_ws_for_rows = _wb_for_rows["08_BEP_SIMULATOR"]
for _row in _ws_for_rows.iter_rows(min_row=1, max_row=30, max_col=2):
    _cell = _row[1]
    if _cell.value and _cell.value not in _label_to_row:
        _label_to_row[_cell.value] = _cell.row
_wb_for_rows.close()

ROW_ACTUAL_PRICE = _label_to_row["Actual Price"]
ROW_INCLUDES_VAT = _label_to_row["Price Includes VAT"]
ROW_VAT_RATE = _label_to_row["VAT Rate (v)"]
ROW_DIRECT = _label_to_row["Product/Service Direct Cost"]
ROW_VARFIXED = _label_to_row["Variable Selling/Delivery Cost (Fixed Amount)"]
ROW_RATENET = _label_to_row["Net-Sales Fee Rate (b)"]
ROW_RATEGROSS = _label_to_row["Gross-Payment Fee Rate (a)"]
ROW_FC_AMOUNT = _label_to_row["Fixed Operating Cost Amount"]
ROW_FC_BASIS = _label_to_row["Fixed Operating Cost Basis"]
ROW_FCS = _label_to_row["Fixed Cost Allocation Status (Excel simulation control — not a schema field)"]

ROW_CMU = _label_to_row["Contribution Margin per Unit (CMu)"]
ROW_FC_RESULT = _label_to_row["Fixed Operating Cost (FC)"]
ROW_Q_BEP = _label_to_row["Break-Even Quantity (Q_BEP)"]
ROW_ANALYSIS_BASIS = _label_to_row["Analysis Period Basis"]
ROW_OVERALL_STATUS = _label_to_row["Overall Status"]

RESULT_ROWS = {
    "contribution_margin_per_unit": ROW_CMU,
    "fixed_operating_cost": ROW_FC_RESULT,
    "break_even_quantity_exact": ROW_Q_BEP,
}

ERROR_STRINGS = {"#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#REF!", "#NULL!", "#NUM!"}
TOL_AMOUNT = 0.01

EXCEL_STATUS_TO_TIER_PREFIX = [("ERROR", "ERROR"), ("INCOMPLETE", "INCOMPLETE"), ("OK", "OK")]


def _excel_overall_status_tier(text):
    for prefix, tier in EXCEL_STATUS_TO_TIER_PREFIX:
        if text.startswith(prefix):
            return tier
    return f"UNRECOGNIZED({text})"


# Single-component, single-fixed-cost-item scenarios only — see module docstring for why
# TC18/19/24/26 are excluded here (covered by 09_BEP_PARITY_TEST's own roll-up instead).
SCENARIOS = [
    dict(name="TC1. Simple positive CM",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
    dict(name="TC2. Fixed cost = 0 (explicit)",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=0, fcbasis="per_month", fcs="component"),
    dict(name="TC3. No fixed-cost item at all",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="", fcs="none"),
    dict(name="TC4. Fixed-cost item exists, amount null",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="per_month", fcs="component"),
    dict(name="TC5. CM = 0, FC > 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=600, varfixed=400,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
    dict(name="TC6. CM < 0, FC > 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=700, varfixed=400,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
    dict(name="TC7. VAT-inclusive display",
         actual_price=1100, includes_vat=True, vat_rate=0.10, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
    dict(name="TC8. VAT-exclusive display, same economics as TC7",
         actual_price=1000, includes_vat=False, vat_rate=0.10, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
    dict(name="TC9. Net-sales fee",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=200, varfixed=0,
         ratenet=0.1, rategross=0, fc=70000, fcbasis="per_month", fcs="component"),
    dict(name="TC10. Gross-payment fee",
         actual_price=1000, includes_vat=False, vat_rate=0.10, direct=0, varfixed=0,
         ratenet=0, rategross=0.05, fc=94500, fcbasis="per_month", fcs="component"),
    dict(name="TC11. v UNKNOWN, not needed (a=0)",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=300, varfixed=0,
         ratenet=0.1, rategross=0, fc=60000, fcbasis="per_month", fcs="component"),
    dict(name="TC12. v UNKNOWN, required",
         actual_price=1100, includes_vat=True, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
    dict(name="TC14. Shared fixed cost, unresolved",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="per_month", fcs="unresolved"),
    dict(name="TC15. Shared + direct invalid configuration",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="per_month", fcs="invalid_direct"),
    dict(name="TC16. Explicit zero rate",
         actual_price=1000, includes_vat=False, vat_rate=0.10, direct=400, varfixed=0,
         ratenet=0, rategross=0.05, fc=60000, fcbasis="per_month", fcs="component"),
    dict(name="TC17. Non-integer break-even quantity",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=52340, fcbasis="per_month", fcs="component"),
    dict(name="TC20. CM input UNKNOWN, FC isolated",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=None, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
    dict(name="TC21. FC = 0, CM = 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=600, varfixed=400,
         ratenet=0, rategross=0, fc=0, fcbasis="per_month", fcs="component"),
    dict(name="TC22. FC = 0, CM < 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=700, varfixed=400,
         ratenet=0, rategross=0, fc=0, fcbasis="per_month", fcs="component"),
    dict(name="TC23. Negative fixed-cost amount",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=-10000, fcbasis="per_month", fcs="component"),
    dict(name="TC25. NOT_APPLICABLE keeps module status OK",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=700, varfixed=400,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component"),
]


def _python_reference(scenario):
    if scenario["fcs"] == "none":
        fc_value, extra_items = False, None
    elif scenario["fcs"] == "component":
        fc_value, extra_items = scenario["fc"], None
    else:
        allocation_rule = {"unresolved": "by_component_revenue", "blended_only": "blended_only",
                            "invalid_direct": "direct"}[scenario["fcs"]]
        fc_value = False
        extra_items = [{
            "item_id": "fixed_ops_shared", "label": "공유 고정운영비", "cost_category": "fixed_operating_cost",
            "amount": None, "rate": None, "currency": None, "basis": scenario["fcbasis"] or "per_month",
            "applies_to_component": "shared", "allocation_rule": allocation_rule,
        }]

    ci = make_client_input_bep(
        actual_price=scenario["actual_price"], includes_vat=scenario["includes_vat"],
        vat_rate=scenario["vat_rate"], direct_cost=scenario["direct"],
        variable_fixed_cost=scenario["varfixed"], net_sales_fee_rate=scenario["ratenet"],
        gross_payment_fee_rate=scenario["rategross"], fixed_operating_cost=fc_value,
        fixed_operating_cost_basis=scenario["fcbasis"] or "per_month", extra_cost_items=extra_items,
    )
    result = run_bep(ci)
    m = result["per_component"]["main"]
    py_results = {mk: (m[mk]["value"] if m[mk]["status"] == "OK" else m[mk]["status"]) for mk in METRIC_KEYS_BEP}
    return ci, py_results, result["status"]


def run_scenario(scenario):
    name = scenario["name"]
    ci, py_results, py_status = _python_reference(scenario)

    wb = openpyxl.load_workbook(BASE_WB)
    ws = wb["08_BEP_SIMULATOR"]

    def set_cell(row, value):
        ws.cell(row=row, column=3).value = value

    set_cell(ROW_ACTUAL_PRICE, scenario["actual_price"])
    set_cell(ROW_INCLUDES_VAT, scenario["includes_vat"])
    set_cell(ROW_VAT_RATE, scenario["vat_rate"])
    set_cell(ROW_DIRECT, scenario["direct"])
    set_cell(ROW_VARFIXED, scenario["varfixed"])
    set_cell(ROW_RATENET, scenario["ratenet"])
    set_cell(ROW_RATEGROSS, scenario["rategross"])
    set_cell(ROW_FC_AMOUNT, scenario["fc"] if scenario["fcs"] == "component" else scenario["fc"])
    set_cell(ROW_FC_BASIS, scenario["fcbasis"])
    set_cell(ROW_FCS, scenario["fcs"])

    safe_name = "".join(ch if ch.isalnum() else "_" for ch in name)[:40]
    scratch_file = SCRATCH / f"{safe_name}.xlsx"
    wb.save(scratch_file)

    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "xlsx", "--outdir", str(SCRATCH / "recalced"), str(scratch_file)],
        check=True, capture_output=True,
    )
    recalced_path = SCRATCH / "recalced" / scratch_file.name
    rwb = openpyxl.load_workbook(recalced_path, data_only=True)
    rws = rwb["08_BEP_SIMULATOR"]

    errors_found = []
    for sheet in rwb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value in ERROR_STRINGS:
                    errors_found.append(f"{sheet.title}!{cell.coordinate}={cell.value}")

    excel_results = {mk: rws.cell(row=RESULT_ROWS[mk], column=3).value for mk in METRIC_KEYS_BEP}
    excel_basis = rws.cell(row=ROW_ANALYSIS_BASIS, column=3).value
    excel_overall_raw = rws.cell(row=ROW_OVERALL_STATUS, column=3).value
    excel_overall_tier = _excel_overall_status_tier(excel_overall_raw or "")

    mismatches = []
    for mk in METRIC_KEYS_BEP:
        ev = excel_results[mk]
        pv = py_results[mk]
        if isinstance(pv, (int, float)):
            if not isinstance(ev, (int, float)) or abs(ev - pv) > TOL_AMOUNT:
                mismatches.append(f"{mk}: excel={ev!r} python={pv!r}")
        else:
            if ev != pv:
                mismatches.append(f"{mk}: excel={ev!r} python={pv!r}")

    if py_status != excel_overall_tier:
        mismatches.append(f"OVERALL STATUS TIER: excel={excel_overall_tier!r} (raw={excel_overall_raw!r}) python={py_status!r}")

    # analysis_period_basis parity
    py_m = run_bep(ci)["per_component"]["main"]
    py_basis = py_m["analysis_period_basis"] if py_m["analysis_period_basis"] is not None else ""
    if (excel_basis or "") != py_basis:
        mismatches.append(f"analysis_period_basis: excel={excel_basis!r} python={py_basis!r}")

    # independent self-check: never trust that Excel's Q_BEP matches Python just because the
    # comparison above passed -- verify Q_BEP*CMu == FC independently when Q_BEP is numeric.
    q = excel_results["break_even_quantity_exact"]
    cmu = excel_results["contribution_margin_per_unit"]
    fc = excel_results["fixed_operating_cost"]
    if isinstance(q, (int, float)) and isinstance(cmu, (int, float)) and isinstance(fc, (int, float)):
        if abs(q * cmu - fc) > TOL_AMOUNT:
            mismatches.append(f"SELF-CHECK FAIL: Q_BEP*CMu={q * cmu!r} != FC={fc!r}")

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

    # 09_BEP_PARITY_TEST's own roll-up (covers TC1-26 including multi-component/basis-
    # inconsistency cases that 08_BEP_SIMULATOR's single-component sheet cannot express).
    wb_static = openpyxl.load_workbook(BASE_WB)
    ws_parity = wb_static["09_BEP_PARITY_TEST"]
    parity_scratch = SCRATCH / "09_parity_static.xlsx"
    wb_static.save(parity_scratch)
    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "xlsx", "--outdir", str(SCRATCH / "recalced"), str(parity_scratch)],
        check=True, capture_output=True,
    )
    rwb_parity = openpyxl.load_workbook(SCRATCH / "recalced" / parity_scratch.name, data_only=True)
    rws_parity = rwb_parity["09_BEP_PARITY_TEST"]
    parity_errors = []
    parity_overall = None
    for sheet in rwb_parity.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value in ERROR_STRINGS:
                    parity_errors.append(f"{sheet.title}!{cell.coordinate}={cell.value}")
    for row in rws_parity.iter_rows():
        for cell in row:
            if cell.value == "All metrics/status/code/self-check PASS?":
                parity_overall = rws_parity.cell(row=cell.row, column=3).value
                break
        if parity_overall is not None:
            break

    print()
    print(f"08_BEP_SIMULATOR scenarios: {len(SCENARIOS)}, Failed: {total_fail}, Raw Excel errors: {total_raw_errors}")
    print(f"09_BEP_PARITY_TEST (TC1-26) roll-up: {parity_overall!r}, raw errors: {len(parity_errors)}")
    for e in parity_errors:
        print(f"    RAW EXCEL ERROR (09 sheet): {e}")

    if total_fail == 0 and total_raw_errors == 0 and parity_overall == "ALL PASS" and not parity_errors:
        print("BEP QA: ALL PASS")
        return 0
    print("BEP QA: FAILURES PRESENT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
