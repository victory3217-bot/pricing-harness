# -*- coding: utf-8 -*-
"""
Scenario Compare Excel Simulator QA driver.

Unlike qa_check.py/qa_check_mode_b.py/qa_check_mode_c.py/qa_check_bep.py, this driver does not
inject scenario-specific inputs into a shared interactive sheet before each recalc — every
10_SCENARIO_COMPARE_PARITY case already carries its own literal base_input/override values,
written once at build time by build_workbook.py (mirroring 07_MODE_C_PARITY_TEST/
09_BEP_PARITY_TEST's own per-case literal-input pattern, just without a second "write inputs into
the interactive sheet" pass, since Scenario Compare has no single-scenario interactive sheet to
drive per case). This driver:

1. Recalculates the saved workbook once via LibreOffice headless.
2. Reads 11_SCENARIO_COMPARE_PARITY's own "All checks PASS?" roll-up cell (built from every
   case's live Excel-vs-Python-reference comparison, docs/features/scenario_compare/CASE.md).
3. Sweeps every sheet for raw Excel error values (#DIV/0!, #VALUE!, #N/A, #NAME?, #REF!, #NULL!,
   #NUM!) — none may ever appear.
4. Independently re-derives a handful of representative cases via a FRESH
   core.engine.scenario_compare.run_scenario_compare() call (not the Python-reference values
   baked into the workbook at build time) and compares those against the recalculated Excel
   cells directly, guarding against a stale/incorrect literal in build_workbook.py itself
   silently agreeing with a matching (but equally stale) Excel formula.
5. Sanity-checks 10_SCENARIO_COMPARE (the interactive sheet) recalculates to its expected
   baseline numbers and workbook open/save round-trips cleanly.
"""
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

from core.engine.scenario_compare import run_scenario_compare  # noqa: E402

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
BASE_WB = HERE / "Pricing_Harness_Excel_Simulator_v0.5.xlsx"
SCRATCH = HERE / "_qa_scratch_sc"

ERROR_STRINGS = {"#DIV/0!", "#VALUE!", "#N/A", "#NAME?", "#REF!", "#NULL!", "#NUM!"}


def _recalc(path):
    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "xlsx", "--outdir", str(SCRATCH), str(path)],
        check=True, capture_output=True,
    )
    return SCRATCH / path.name


def _sweep_raw_errors(wb):
    errors = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value in ERROR_STRINGS:
                    errors.append(f"{sheet.title}!{cell.coordinate}={cell.value}")
    return errors


def _make_client_input(values):
    return {
        "schema_version": "1.1", "client_id": "excel_qa", "case_id": "excel_qa_sc",
        "product": {"name": "sc_qa", "pricing_model": "one_time", "price_components": [{
            "component_id": "main", "type": "one_time", "actual_price": values["p"],
            "target_market_price": values["tmp"], "currency": "KRW",
            "price_includes_vat": values["incvat"], "discount_rate": values["disc"],
        }]},
        "tax": {"vat_rate": values["v"]},
        "fx": {"base_currency": "KRW", "reporting_currency": "KRW", "rate_base_per_reporting": 1},
        "costs": {"items": [
            {"item_id": "direct", "label": "직접원가", "cost_category": "product_service_direct_cost",
             "amount": values["direct"], "rate": None, "currency": "KRW", "basis": "per_unit", "applies_to_component": "main"},
            {"item_id": "var_fixed", "label": "변동비", "cost_category": "variable_selling_delivery",
             "amount": values["varfixed"], "rate": None, "currency": "KRW", "basis": "per_order", "applies_to_component": "main"},
            {"item_id": "var_net_sales", "label": "매출액기준", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": values["ratenet"], "currency": None, "basis": "rate_of_net_sales", "applies_to_component": "main"},
            {"item_id": "var_gross_payment", "label": "결제액기준", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": values["rategross"], "currency": None, "basis": "rate_of_gross_payment", "applies_to_component": "main"},
            {"item_id": "fixed_ops", "label": "고정운영비", "cost_category": "fixed_operating_cost",
             "amount": values["fc"], "rate": None, "currency": "KRW", "basis": "per_month", "applies_to_component": "main"},
        ]},
        "targets": {"target_contribution_margin_rate": values["tcm"]},
        "meta": {},
    }


DEFAULT_BASE_VALUES = {
    "p": 1000, "incvat": False, "v": 0.10, "tmp": 1000, "disc": 0, "direct": 400,
    "varfixed": 100, "ratenet": 0, "rategross": 0, "fc": 50000, "tcm": 0.3,
}

# A handful of representative cases, independently re-derived here (fresh Python call) and
# compared directly against the recalculated 10_SCENARIO_COMPARE interactive sheet -- this sheet
# always represents scenarios A/B/C as "baseline (no override)", "price 1200", "price 800 +
# direct cost 300" respectively (build_workbook.py's default example inputs), so the comparison
# below targets exactly that fixed scenario shape.
INDEPENDENT_CASES = [
    dict(name="Interactive sheet Scenario A (baseline, no overrides)",
         request={"base_input": _make_client_input(DEFAULT_BASE_VALUES), "baseline_scenario_id": "A",
                  "scenarios": [{"scenario_id": "A", "label": "A"}, {"scenario_id": "B", "label": "B",
                  "overrides": {"components": [{"component_id": "main", "actual_price": 1200}]}}]},
         expect_scenario_id="A", expect_cm=500, expect_qbep=100),
    dict(name="Interactive sheet Scenario B (price up to 1200)",
         request={"base_input": _make_client_input(DEFAULT_BASE_VALUES), "baseline_scenario_id": "A",
                  "scenarios": [{"scenario_id": "A", "label": "A"}, {"scenario_id": "B", "label": "B",
                  "overrides": {"components": [{"component_id": "main", "actual_price": 1200}]}}]},
         expect_scenario_id="B", expect_cm=700, expect_qbep=100 * 500 / 700),
]


def main():
    if SCRATCH.exists():
        import shutil
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)

    recalced_path = _recalc(BASE_WB)
    wb = openpyxl.load_workbook(recalced_path, data_only=True)

    total_fail = 0

    # 1/2. 11_SCENARIO_COMPARE_PARITY roll-up
    ws_parity = wb["11_SCENARIO_COMPARE_PARITY"]
    overall_cell_value = None
    for row in ws_parity.iter_rows():
        for cell in row:
            if cell.value == "All checks PASS?":
                overall_cell_value = ws_parity.cell(row=cell.row, column=3).value
    print(f"11_SCENARIO_COMPARE_PARITY roll-up: {overall_cell_value!r}")
    if overall_cell_value != "ALL PASS":
        total_fail += 1

    fail_cells = []
    for row in ws_parity.iter_rows():
        for cell in row:
            if cell.value == "FAIL":
                fail_cells.append(cell.coordinate)
    print(f"11_SCENARIO_COMPARE_PARITY individual FAIL cells: {len(fail_cells)}")
    if fail_cells:
        total_fail += 1
        for c in fail_cells[:20]:
            print(f"    FAIL: {c}")

    # 3. raw error sweep, whole workbook
    raw_errors = _sweep_raw_errors(wb)
    print(f"Raw Excel errors (whole workbook): {len(raw_errors)}")
    for e in raw_errors[:20]:
        print(f"    RAW EXCEL ERROR: {e}")
    if raw_errors:
        total_fail += 1

    # 4. independent re-derivation for representative cases against 10_SCENARIO_COMPARE
    ws_interactive = wb["10_SCENARIO_COMPARE"]
    _label_to_row = {}
    for r in ws_interactive.iter_rows(min_row=1, max_row=60, max_col=2):
        cell = r[1]
        if cell.value and cell.value not in _label_to_row:
            _label_to_row[cell.value] = cell.row
    row_cm = _label_to_row["MODE A: Contribution Margin"]
    row_qbep = _label_to_row["BEP: Break-Even Quantity"]
    scenario_col = {"A": 3, "B": 4, "C": 5, "D": 6, "E": 7}

    for case in INDEPENDENT_CASES:
        py_result = run_scenario_compare(case["request"])
        py_scenario = next(s for s in py_result["scenarios"] if s["scenario_id"] == case["expect_scenario_id"])
        py_cm = py_scenario["summary"]["per_component"]["main"]["mode_a"]["contribution_margin"]["value"]
        py_qbep = py_scenario["summary"]["per_component"]["main"]["bep"]["break_even_quantity_exact"]["value"]

        col = scenario_col[case["expect_scenario_id"]]
        excel_cm = ws_interactive.cell(row=row_cm, column=col).value
        excel_qbep = ws_interactive.cell(row=row_qbep, column=col).value

        ok = (
            abs(excel_cm - py_cm) <= 0.01 and abs(excel_cm - case["expect_cm"]) <= 0.01
            and abs(excel_qbep - py_qbep) <= 0.01 and abs(excel_qbep - case["expect_qbep"]) <= 0.01
        )
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['name']}: excel(cm={excel_cm}, qbep={excel_qbep}) "
              f"python(cm={py_cm}, qbep={py_qbep}) expected(cm={case['expect_cm']}, qbep={case['expect_qbep']})")
        if not ok:
            total_fail += 1

    # 4b. TC37 (invalid baseline, STEP-3 / CASE.md TC37) independent diagnostic -- fresh
    # run_scenario_compare() call, compared directly against 11_SCENARIO_COMPARE_PARITY's own
    # TC37 columns (J=W baseline, K=B, L=D) after the same recalculated-workbook load used above.
    # This is separate from PARITY_CASES_SC's own baked-in-reference comparison rows (which the
    # roll-up in step 1/2 already covers): it re-derives the invariant that matters most --
    # invalid baseline does not corrupt valid siblings' absolute results, but does force their
    # baseline-dependent deltas to ERROR -- from a live Python call, not a value written into the
    # workbook at build time.
    ws_parity = wb["11_SCENARIO_COMPARE_PARITY"]
    tc37_row = None
    for row in ws_parity.iter_rows():
        for cell in row:
            if cell.value == "TC37. Invalid baseline (STEP-3) -- CASE.md TC37":
                tc37_row = cell.row
    if tc37_row is None:
        print("[FAIL] TC37 independent diagnostic: could not locate TC37 section header")
        total_fail += 1
    else:
        tc37_req = {
            "base_input": _make_client_input(DEFAULT_BASE_VALUES),
            "baseline_scenario_id": "W",
            "scenarios": [
                {"scenario_id": "W", "label": "W", "overrides": {
                    "cost_items": [{"item_id": "var_gross_payment", "rate": 1.5}]}},
                {"scenario_id": "B", "label": "B", "overrides": {
                    "components": [{"component_id": "main", "actual_price": 1200}]}},
                {"scenario_id": "D", "label": "D", "overrides": {
                    "cost_items": [{"item_id": "direct", "amount": 300}]}},
            ],
        }
        tc37_py = run_scenario_compare(tc37_req)
        w_scn = next(s for s in tc37_py["scenarios"] if s["scenario_id"] == "W")
        b_scn = next(s for s in tc37_py["scenarios"] if s["scenario_id"] == "B")

        # Find the "Scenario B: contribution_margin" / "Scenario B: break_even_quantity_exact" /
        # "Scenario B: contribution_margin_delta" / "Scenario B: net_sales_ex_vat_delta" rows by
        # their own labels in column B, and read the live Excel value already recalculated next
        # to each (column C).
        _sc_label_to_row = {}
        for r_ in range(tc37_row, tc37_row + 120):
            v = ws_parity.cell(row=r_, column=2).value
            if v:
                _sc_label_to_row[v] = r_

        checks = []

        def _get(label_text):
            r_ = _sc_label_to_row.get(label_text)
            return ws_parity.cell(row=r_, column=3).value if r_ else None

        py_b_cm = b_scn["summary"]["per_component"]["main"]["mode_a"]["contribution_margin"]["value"]
        py_b_qbep = b_scn["summary"]["per_component"]["main"]["bep"]["break_even_quantity_exact"]["value"]
        excel_b_cm = _get("Scenario B: contribution_margin")
        excel_b_qbep = _get("Scenario B: break_even_quantity_exact")
        checks.append(("Scenario B absolute contribution_margin", excel_b_cm, py_b_cm,
                        isinstance(excel_b_cm, (int, float)) and abs(excel_b_cm - py_b_cm) <= 0.01))
        checks.append(("Scenario B absolute break_even_quantity_exact", excel_b_qbep, py_b_qbep,
                        isinstance(excel_b_qbep, (int, float)) and abs(excel_b_qbep - py_b_qbep) <= 0.01))

        py_b_cm_delta_status = b_scn["deltas"]["per_component"]["main"]["contribution_margin_delta"]["status"]
        py_b_qbep_delta_status = b_scn["deltas"]["per_component"]["main"]["break_even_quantity_delta"]["status"]
        excel_b_cm_delta = _get("Scenario B: contribution_margin_delta")
        excel_b_qbep_delta = _get("Scenario B: break_even_quantity_delta")
        checks.append(("Scenario B contribution_margin_delta status", excel_b_cm_delta, py_b_cm_delta_status,
                        excel_b_cm_delta == "ERROR" and py_b_cm_delta_status == "ERROR"))
        checks.append(("Scenario B break_even_quantity_delta status", excel_b_qbep_delta, py_b_qbep_delta_status,
                        excel_b_qbep_delta == "ERROR" and py_b_qbep_delta_status == "ERROR"))

        excel_w_status = _get("Scenario W: scenario_status")
        checks.append(("Baseline W scenario_status", excel_w_status, w_scn["scenario_status"],
                        excel_w_status == "ERROR" and w_scn["scenario_status"] == "ERROR"))

        warning_count = sum(1 for w2 in tc37_py["warnings"] if w2["code"] == "BASELINE_SCENARIO_INVALID_FOR_DELTA")
        checks.append(("BASELINE_SCENARIO_INVALID_FOR_DELTA warning count", warning_count, 1, warning_count == 1))

        print("TC37 independent diagnostic (fresh run_scenario_compare(), live Excel):")
        for name, excel_v, py_v, ok in checks:
            status = "PASS" if ok else "FAIL"
            print(f"    [{status}] {name}: excel={excel_v!r} python={py_v!r}")
            if not ok:
                total_fail += 1

    # 5. workbook open/save sanity
    try:
        wb2 = openpyxl.load_workbook(BASE_WB)
        assert len(wb2.sheetnames) == 12
        wb2.save(BASE_WB)
        print(f"Workbook open/save OK, sheet count: {len(wb2.sheetnames)}")
    except Exception as e:
        print(f"Workbook open/save FAILED: {e}")
        total_fail += 1

    print()
    if total_fail == 0:
        print("SCENARIO COMPARE QA: ALL PASS")
        return 0
    print("SCENARIO COMPARE QA: FAILURES PRESENT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
