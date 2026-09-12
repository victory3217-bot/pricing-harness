# -*- coding: utf-8 -*-
"""
STEP 5-6 QA driver.

For each scenario: write the scenario's inputs into a fresh copy of 01_SIMULATOR's live
input cells, force a LibreOffice recalculation, read the recalculated RESULT/STATUS cells
back, and compare against core/engine/modes/mode_a.py run on the equivalent Client Input.
Also sweeps every recalculated cell in every scenario for a raw Excel error value
(#DIV/0!, #VALUE!, #N/A, #NAME?, #REF!, #NULL!, #NUM!) — none may ever appear.

Also compares module-status TIER: Python's run_mode_a(ci)["status"] (canonical 3-tier —
OK / INCOMPLETE / ERROR, dependency_rules.md section 5) against Excel's "Data Complete /
Incomplete / Error" cell (Complete / Incomplete / Error), normalized to the same 3-tier vocabulary
before comparing. None of these 9 scenarios currently produce a Python ERROR module status (no
scenario here uses a shared+direct cost item or an actual_price_ex_vat == 0 edge case), so this
mainly pins OK<->Complete and INCOMPLETE<->Incomplete for now — see qa_check_mode_b.py for the
ERROR-tier cases, which MODE B's 04_MODE_B_SIMULATOR can represent and MODE A's 01_SIMULATOR
currently cannot (no shared-cost input exists on that sheet).
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

from core.engine.modes.mode_a import run_mode_a  # noqa: E402
from scenario_helpers import make_client_input, METRIC_KEYS  # noqa: E402

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
BASE_WB = HERE / "Pricing_Harness_Excel_Simulator_v0.5.xlsx"
SCRATCH = HERE / "_qa_scratch"

# 01_SIMULATOR input cell rows (must match build_workbook.py's layout)
ROW_ACTUAL_PRICE = 6
ROW_INCLUDES_VAT = 7
ROW_VAT_RATE = 8
ROW_DIRECT_COST = 9
ROW_CHANNEL_FEE = 10
ROW_PG_FEE = 11
ROW_DELIVERY = 12
ROW_OTHER_VAR = 13

ROW_EX_VAT = 16
ROW_DIRECT_TOTAL = 17
ROW_GROSS_PROFIT = 18
ROW_GP_RATE = 19
ROW_VAR_TOTAL = 20
ROW_CM = 21
ROW_CM_RATE = 22
ROW_STATUS_COMPLETE = 25
ROW_STATUS_MISSING = 26
ROW_STATUS_WARNING = 27

RESULT_ROWS = {
    "actual_price_ex_vat": ROW_EX_VAT,
    "direct_cost_total": ROW_DIRECT_TOTAL,
    "gross_profit": ROW_GROSS_PROFIT,
    "gross_profit_rate": ROW_GP_RATE,
    "variable_cost_total": ROW_VAR_TOTAL,
    "contribution_margin": ROW_CM,
    "contribution_margin_rate": ROW_CM_RATE,
}

ERROR_STRINGS = {"#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#REF!", "#NULL!", "#NUM!"}

SCENARIOS = [
    dict(name="1. Normal input (all known)",
         actual_price=50000, includes_vat=True, vat_rate=0.10, direct_cost=20000,
         channel_fee_rate=0.05, pg_fee_rate=0.02, delivery=1500, other_var=0),
    dict(name="2. VAT-inclusive price",
         actual_price=22000, includes_vat=True, vat_rate=0.10, direct_cost=9000,
         channel_fee_rate=0, pg_fee_rate=0.03, delivery=0, other_var=0),
    dict(name="3. VAT-exclusive price + VAT rate blank",
         actual_price=20000, includes_vat=False, vat_rate=None, direct_cost=9000,
         channel_fee_rate=0, pg_fee_rate=0.03, delivery=0, other_var=0),
    dict(name="4. Direct cost blank",
         actual_price=35000, includes_vat=True, vat_rate=0.10, direct_cost=None,
         channel_fee_rate=0, pg_fee_rate=0.025, delivery=3000, other_var=0),
    dict(name="5. Fee rate blank (PG fee)",
         actual_price=35000, includes_vat=True, vat_rate=0.10, direct_cost=13500,
         channel_fee_rate=0, pg_fee_rate=None, delivery=3000, other_var=0),
    dict(name="6. Explicit zero cost (not UNKNOWN)",
         actual_price=35000, includes_vat=True, vat_rate=0.10, direct_cost=13500,
         channel_fee_rate=0, pg_fee_rate=0, delivery=0, other_var=0),
    dict(name="7. Ecommerce (channel fee + PG fee, different bases)",
         actual_price=59000, includes_vat=True, vat_rate=0.10, direct_cost=17000,
         channel_fee_rate=0.13, pg_fee_rate=0.028, delivery=2500, other_var=0),
    dict(name="8. Fully incomplete (all blank)",
         actual_price=35000, includes_vat=None, vat_rate=None, direct_cost=None,
         channel_fee_rate=None, pg_fee_rate=None, delivery=None, other_var=None),
    # 9 regression-tests the corrected gross-payment VAT rule: a positive check that the
    # fee is actually computed on the grossed-up base (selling_price*(1+v)), not on
    # selling_price alone. Scenario 3 above already regression-tests the UNKNOWN-propagation
    # half of the same fix (vat_rate blank + gross-payment fee -> now correctly UNKNOWN,
    # where it used to wrongly compute a number).
    dict(name="9. VAT-exclusive display + known VAT rate + gross-payment fee",
         actual_price=8800, includes_vat=False, vat_rate=0.10, direct_cost=3000,
         channel_fee_rate=0, pg_fee_rate=0.04, delivery=200, other_var=0),
    # 10 exercises MODE A's genuine ERROR path (dependency_rules.md section 5's 3-tier rule,
    # Python side: mode_a.py's gross_profit_rate/contribution_margin_rate go ERROR, code
    # CALCULATION_ERROR, when actual_price_ex_vat == 0 -- a known input, not a missing one,
    # dividing by a confirmed zero). Requires the GP_RATE/CM_RATE Excel formula fix (see
    # build_workbook.py) that distinguishes this from "not yet a number" (UNKNOWN/미입력).
    dict(name="10. actual_price_ex_vat == 0 -> gross_profit_rate/contribution_margin_rate ERROR",
         actual_price=0, includes_vat=False, vat_rate=0.10, direct_cost=4000,
         channel_fee_rate=0, pg_fee_rate=0, delivery=0, other_var=0),
]

TOL_AMOUNT = 0.01
TOL_RATE = 0.0001
RATE_METRICS = {"gross_profit_rate", "contribution_margin_rate"}

EXCEL_STATUS_TO_TIER = {"Complete": "OK", "Incomplete": "INCOMPLETE", "Error": "ERROR"}


def run_scenario(scenario):
    name = scenario["name"]
    params = {k: v for k, v in scenario.items() if k != "name"}

    wb = openpyxl.load_workbook(BASE_WB)
    ws = wb["01_SIMULATOR"]

    def set_cell(row, value):
        # NOTE: ws.cell(row, col, value=None) is a no-op in openpyxl (None is the
        # sentinel "don't set" default for that parameter) — it does NOT clear the
        # cell. Must assign .value directly to actually blank a cell out.
        cell = ws.cell(row=row, column=3)
        cell.value = value

    set_cell(ROW_ACTUAL_PRICE, params["actual_price"])
    set_cell(ROW_INCLUDES_VAT, params["includes_vat"])
    set_cell(ROW_VAT_RATE, params["vat_rate"])
    set_cell(ROW_DIRECT_COST, params["direct_cost"])
    set_cell(ROW_CHANNEL_FEE, params["channel_fee_rate"])
    set_cell(ROW_PG_FEE, params["pg_fee_rate"])
    set_cell(ROW_DELIVERY, params["delivery"])
    set_cell(ROW_OTHER_VAR, params["other_var"])

    safe_name = "".join(ch if ch.isalnum() else "_" for ch in name)[:40]
    scratch_file = SCRATCH / f"{safe_name}.xlsx"
    wb.save(scratch_file)

    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "xlsx", "--outdir", str(SCRATCH / "recalced"), str(scratch_file)],
        check=True, capture_output=True,
    )
    recalced_path = SCRATCH / "recalced" / scratch_file.name
    rwb = openpyxl.load_workbook(recalced_path, data_only=True)
    rws = rwb["01_SIMULATOR"]

    # sweep every cell on every sheet of the recalculated workbook for a raw Excel error
    errors_found = []
    for sheet in rwb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value in ERROR_STRINGS:
                    errors_found.append(f"{sheet.title}!{cell.coordinate}={cell.value}")

    excel_results = {mk: rws.cell(row=RESULT_ROWS[mk], column=3).value for mk in METRIC_KEYS}
    status_complete = rws.cell(row=ROW_STATUS_COMPLETE, column=3).value
    status_missing = rws.cell(row=ROW_STATUS_MISSING, column=3).value
    status_warning = rws.cell(row=ROW_STATUS_WARNING, column=3).value

    ci = make_client_input(**params)
    py_full = run_mode_a(ci)
    py_result = py_full["per_component"]["main"]
    py_module_status = py_full["status"]

    rows = []
    all_ok = True
    for mk in METRIC_KEYS:
        py_status = py_result[mk]["status"]
        py_value = py_result[mk]["value"]
        excel_value = excel_results[mk]
        excel_is_number = isinstance(excel_value, (int, float)) and not isinstance(excel_value, bool)

        if py_status == "OK":
            tol = TOL_RATE if mk in RATE_METRICS else TOL_AMOUNT
            ok = excel_is_number and abs(excel_value - py_value) <= tol
        else:
            ok = not excel_is_number  # engine says UNKNOWN -> Excel must show non-numeric ("미입력"/"계산불가")
        all_ok = all_ok and ok
        rows.append((mk, py_status, py_value, excel_value, "PASS" if ok else "FAIL"))

    excel_module_tier = EXCEL_STATUS_TO_TIER.get(status_complete, f"UNRECOGNIZED({status_complete})")
    module_status_ok = excel_module_tier == py_module_status
    all_ok = all_ok and module_status_ok

    if errors_found:
        all_ok = False

    return {
        "name": name, "rows": rows, "all_ok": all_ok, "errors_found": errors_found,
        "status_complete": status_complete, "status_missing": status_missing, "status_warning": status_warning,
        "py_module_status": py_module_status, "excel_module_tier": excel_module_tier,
        "module_status_ok": module_status_ok,
    }


def main():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir()
    (SCRATCH / "recalced").mkdir()

    sys.stdout.reconfigure(encoding="utf-8")
    overall_pass = True
    for scenario in SCENARIOS:
        result = run_scenario(scenario)
        overall_pass = overall_pass and result["all_ok"]
        print(f"\n=== {result['name']} ===  {'PASS' if result['all_ok'] else 'FAIL'}")
        print(f"  Status: {result['status_complete']} | Missing: {result['status_missing']} | Warning: {result['status_warning']}")
        print(f"  Module status tier: python={result['py_module_status']}  excel={result['excel_module_tier']}  "
              f"{'PASS' if result['module_status_ok'] else 'FAIL'}")
        for mk, py_status, py_value, excel_value, verdict in result["rows"]:
            print(f"  {mk:28} python={py_status:8}{py_value!s:>18}  excel={excel_value!s:>18}  {verdict}")
        if result["errors_found"]:
            print("  !! RAW EXCEL ERRORS FOUND:", result["errors_found"])

    print("\n" + "=" * 60)
    print("OVERALL:", "ALL SCENARIOS PASS" if overall_pass else "SOME SCENARIOS FAILED")
    shutil.rmtree(SCRATCH)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
