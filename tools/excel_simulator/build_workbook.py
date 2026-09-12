# -*- coding: utf-8 -*-
"""
Builds the Pricing Harness Excel Simulator v0.2 (MODE A + MODE B).

Excel is the "Interactive Simulation Layer" (see 00_GUIDE / architecture note): its formulas
must mirror docs/features/mode_a_current_price/SPEC.md and core/engine/modes/mode_a.py exactly.
This script does not read the Python engine at runtime — parity is verified separately by
03_PARITY_TEST, which hardcodes the Python engine's actual output (captured from
core/schemas/examples/analysis_results/) next to Excel's own live formula recomputation of the
same scenario.
"""
import openpyxl
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

NAVY = "0B3D5C"
TEAL = "1C93C2"
BROWN = "6B4A3A"
YELLOW = "FFF6CC"
LIGHT = "F7FAFC"
GREY = "5B6B77"
WHITE = "FFFFFF"
GREEN_BG = "E6F4EA"
RED_BG = "FBE7E4"
INK = "1B2A38"

title_font = Font(name="Calibri", size=16, bold=True, color=WHITE)
title_fill = PatternFill("solid", fgColor=NAVY)
section_font = Font(name="Calibri", size=12, bold=True, color=WHITE)
section_fill = PatternFill("solid", fgColor=TEAL)
label_font = Font(name="Calibri", size=11, color=INK)
value_font = Font(name="Calibri", size=11, bold=True, color=INK)
note_font = Font(name="Calibri", size=9, italic=True, color=GREY)
header_font = Font(name="Calibri", size=11, bold=True, color=WHITE)
header_fill = PatternFill("solid", fgColor=NAVY)
input_fill = PatternFill("solid", fgColor=YELLOW)
thin = Side(style="thin", color="D9E2E8")
box = Border(left=thin, right=thin, top=thin, bottom=thin)


def title_row(ws, row, text, span=6):
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=1 + span)
    c = ws.cell(row=row, column=2, value=text)
    c.font = title_font
    c.fill = title_fill
    c.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[row].height = 26
    for col in range(2, 2 + span):
        ws.cell(row=row, column=col).fill = title_fill


def section_row(ws, row, text, span=3):
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=1 + span)
    c = ws.cell(row=row, column=2, value=text)
    c.font = section_font
    c.fill = section_fill
    c.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[row].height = 20
    for col in range(2, 2 + span):
        ws.cell(row=row, column=col).fill = section_fill


def label(ws, row, col, text, italic=False, wrap=False):
    c = ws.cell(row=row, column=col, value=text)
    # Defensive: a plain-text label starting with "=" (or +, -, @) is silently reinterpreted
    # as a formula by Excel/LibreOffice on open — this bit us once already (produced #N/A /
    # #VALUE! in the note column). Force the string type explicitly so it can't recur.
    if isinstance(text, str) and text[:1] in ("=", "+", "-", "@"):
        c.data_type = "s"
    c.font = note_font if italic else label_font
    c.alignment = Alignment(vertical="center", wrap_text=wrap)
    return c


def input_cell(ws, row, col, value=None, fmt=None, note=None):
    c = ws.cell(row=row, column=col, value=value)
    c.font = value_font
    c.fill = input_fill
    c.border = box
    c.alignment = Alignment(vertical="center", horizontal="right")
    if fmt:
        c.number_format = fmt
    return c


def formula_cell(ws, row, col, formula, fmt=None, bold=True, fill=None):
    c = ws.cell(row=row, column=col, value=formula)
    c.font = value_font if bold else label_font
    c.border = box
    c.alignment = Alignment(vertical="center", horizontal="right")
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = PatternFill("solid", fgColor=fill)
    return c


def build_mode_b_formulas(ws, cell_map, refs):
    """Writes MODE B's formula chain (SPEC.md section 3-6 / core/engine/modes/mode_b.py) into
    `ws` at the (row, col) positions given per metric key in `cell_map`, using the input cell
    references in `refs` (t, c, b, a, v, incvat, disc, shared_flag — see docs/features/
    mode_b_target_price/SPEC.md for symbol meanings). Returns {metric_key: cell_coordinate}.
    Shared by 04_MODE_B_SIMULATOR (direct visible display, one column) and
    05_MODE_B_PARITY_TEST (a hidden helper row, one column per metric) so both use the exact
    same formula strings — they can never silently drift apart from each other.

    Every cell holds either a number or one of the text strings "UNKNOWN"/"ERROR" (Excel raw
    errors like #DIV/0! are never surfaced — see the module docstring / GUIDE 'blank != 0'
    section). ERROR conditions (SPEC.md section 6): t<0 or t>=1, b<0, a<0, C<0, D<=0,
    discount_rate<0 or >=1, shared_flag="invalid". UNKNOWN conditions: any required input
    blank, shared_flag="unresolved", or the per-metric VAT dependency in SPEC.md section 5 (N
    needs v only if a>0; G always needs v; required_selling_price needs price_includes_vat,
    then whichever of N/G it points to).

    `refs["shared_flag"]` stands in for the shared-cost-allocation status a real Client Input
    would carry on its cost items (see dependency_rules.md section 4 / SPEC.md section 9) — it
    is NOT an allocation engine; it only tests that MODE B never turns an unsupported/invalid
    shared-cost configuration into a silently-generated number. "none" (the default) behaves
    exactly like the original formula with no shared-cost complication; "unresolved" forces
    denominator (and everything downstream of it) to UNKNOWN, matching an unresolved
    by_component_revenue/fixed_share item; "invalid" forces denominator (and downstream) to
    ERROR, matching an applies_to_component=shared + allocation_rule=direct configuration
    (INVALID_ALLOCATION_CONFIGURATION in core/engine/modes/mode_b.py).

    expected_contribution_margin is deliberately NOT "= t * N" — that would just restore the
    target rate MODE B was solving for, which cannot catch an arithmetic error in the N
    inversion itself. It is instead recomputed independently from the actual cost structure
    (CM = N - C - bN - aG, the same CM identity SPEC.md derives *before* solving for N), so the
    inversion (N = C/D) and the verification (CM = N-C-bN-aG, CMR = CM/N) are two independent
    calculation paths that must agree — see the separate self-check diagnostic this function's
    callers add (|CMR - t| <= tolerance), which is exactly the check that would fail if they
    didn't.
    """
    t, c, b, a, v, incvat, disc, flag = (
        refs["t"], refs["c"], refs["b"], refs["a"], refs["v"], refs["incvat"], refs["disc"], refs["shared_flag"],
    )

    def put(key, formula):
        row, col = cell_map[key]
        return ws.cell(row=row, column=col, value=formula).coordinate

    d_formula = (
        f'=IFERROR('
        f'IF({flag}="invalid","ERROR",'
        f'IF({flag}="unresolved","UNKNOWN",'
        f'IF(OR(AND(NOT(ISBLANK({t})),OR({t}<0,{t}>=1)),AND(NOT(ISBLANK({b})),{b}<0),'
        f'AND(NOT(ISBLANK({a})),{a}<0),AND(NOT(ISBLANK({c})),{c}<0)),"ERROR",'
        f'IF(OR(ISBLANK({t}),ISBLANK({b}),ISBLANK({a})),"UNKNOWN",'
        f'IF({a}=0,'
        f'IF(1-{t}-{b}<=0,"ERROR",1-{t}-{b}),'
        f'IF(ISBLANK({v}),"UNKNOWN",'
        f'IF(1-{t}-{b}-{a}*(1+{v})<=0,"ERROR",1-{t}-{b}-{a}*(1+{v}))))))'
        f')),"ERROR")'
    )
    d_cell = put("denominator", d_formula)

    n_formula = f'=IFERROR(IF(ISBLANK({c}),"UNKNOWN",IF(NOT(ISNUMBER({d_cell})),{d_cell},{c}/{d_cell})),"ERROR")'
    n_cell = put("required_net_sales_ex_vat", n_formula)

    g_formula = (
        f'=IFERROR(IF(NOT(ISNUMBER({n_cell})),{n_cell},'
        f'IF(ISBLANK({v}),"UNKNOWN",{n_cell}*(1+{v}))),"ERROR")'
    )
    g_cell = put("required_gross_payment_incl_vat", g_formula)

    s_formula = f'=IFERROR(IF(ISBLANK({incvat}),"UNKNOWN",IF({incvat}=FALSE,{n_cell},{g_cell})),"ERROR")'
    s_cell = put("required_selling_price", s_formula)

    l_formula = (
        f'=IFERROR(IF(NOT(ISNUMBER({s_cell})),{s_cell},'
        f'IF(ISBLANK({disc}),"UNKNOWN",'
        f'IF(OR({disc}<0,{disc}>=1),"ERROR",'
        f'IF({disc}=0,{s_cell},{s_cell}/(1-{disc}))))),"ERROR")'
    )
    l_cell = put("required_list_price", l_formula)

    # CM = N - C - b*N - a*G (independent economic recompute, NOT t*N — see docstring). When
    # a=0, G must not even be referenced: a=0 mathematically makes the a*G term vanish, but
    # Excel would otherwise evaluate 0*"UNKNOWN"/0*"ERROR" (G can be non-numeric when a=0 and v
    # is blank) and raise a raw #VALUE! error.
    cm_formula = (
        f'=IFERROR(IF(NOT(ISNUMBER({n_cell})),{n_cell},'
        f'IF({a}=0,{n_cell}-{c}-{b}*{n_cell},'
        f'IF(NOT(ISNUMBER({g_cell})),{g_cell},{n_cell}-{c}-{b}*{n_cell}-{a}*{g_cell}))),"ERROR")'
    )
    cm_cell = put("expected_contribution_margin", cm_formula)

    cmr_formula = (
        f'=IFERROR(IF(NOT(ISNUMBER({cm_cell})),{cm_cell},'
        f'IF({n_cell}=0,"ERROR",{cm_cell}/{n_cell})),"ERROR")'
    )
    cmr_cell = put("expected_contribution_margin_rate", cmr_formula)

    return {
        "denominator": d_cell, "required_net_sales_ex_vat": n_cell,
        "required_gross_payment_incl_vat": g_cell, "required_selling_price": s_cell,
        "required_list_price": l_cell, "expected_contribution_margin": cm_cell,
        "expected_contribution_margin_rate": cmr_cell,
    }


def build_self_check_cell(ws, row, col, cmr_cell, t_ref, tol=0.0001):
    """Diagnostic only (not one of MODE B's official output metrics): does the independently
    recomputed CMR (= CM/N, from build_mode_b_formulas) land within `tol` of the target rate t
    that N was solved for? PASS/FAIL when both are numbers, N/A when CMR is UNKNOWN/ERROR."""
    formula = (
        f'=IF(NOT(ISNUMBER({cmr_cell})),"N/A",'
        f'IF(ABS({cmr_cell}-{t_ref})<={tol},"PASS","FAIL"))'
    )
    return ws.cell(row=row, column=col, value=formula).coordinate


def _unknown_blank(ref):
    """Missing-value test for a raw literal input cell (MODE B/C/BEP's own simulator/parity
    sheets feed genuinely blank-able input cells into their formula chains)."""
    return f"ISBLANK({ref})"


def _unknown_num_sentinel(ref):
    """Missing-value test for a numeric formula cell (Scenario Compare's `eff_*` cells are
    never literally blank -- an omitted/explicit-null override surfaces as the literal text
    'UNKNOWN' instead, which ISNUMBER also correctly rejects alongside any upstream 'ERROR')."""
    return f"NOT(ISNUMBER({ref}))"


def _unknown_bool_sentinel(ref):
    """Missing-value test for a price_includes_vat-shaped formula cell -- same formula-cell
    reasoning as _unknown_num_sentinel, but TRUE/FALSE is not itself numeric, so the sentinel is
    tested by direct string equality instead of ISNUMBER."""
    return f'{ref}="UNKNOWN"'


def _price_basis_formulas(p, incvat, v, unknown_num, unknown_bool):
    """Shared N (ex-VAT net sales) / G (VAT-inclusive gross payment) price-basis formula pair --
    the same 'price -> N/G' identity used by MODE A, MODE C's market-price basis, and BEP
    (docs/features/*/SPEC.md's common price-basis derivation; also reused by Scenario Compare's
    per-scenario MODE A and MODE C blocks). `unknown_num`/`unknown_bool` supply the caller's own
    missing-value test for the numeric (p, v) and boolean (incvat) refs respectively -- see
    _unknown_blank (raw literal-input sheets) vs _unknown_num_sentinel/_unknown_bool_sentinel
    (Scenario Compare's already-evaluated, sentinel-bearing formula cells) -- the only axis that
    legitimately differs between callers; the N/G math itself is identical everywhere. Returns
    (n_formula, g_formula), not yet written to any cell."""
    n_formula = (
        f'=IFERROR(IF({unknown_num(p)},"UNKNOWN",'
        f'IF({unknown_bool(incvat)},"UNKNOWN",'
        f'IF({incvat}=FALSE,{p},'
        f'IF({unknown_num(v)},"UNKNOWN",{p}/(1+{v}))))),"ERROR")'
    )
    g_formula = (
        f'=IFERROR(IF({unknown_num(p)},"UNKNOWN",'
        f'IF({unknown_bool(incvat)},"UNKNOWN",'
        f'IF({incvat}=TRUE,{p},'
        f'IF({unknown_num(v)},"UNKNOWN",{p}*(1+{v}))))),"ERROR")'
    )
    return n_formula, g_formula


def _cmu_formula(n_cell, direct, varfixed, ratenet, rategross, g_cell, unknown_num, extra_unknown_refs=()):
    """Shared contribution-margin-per-unit formula: CMu = N - direct - varfixed - b*N - a*G
    (a=0 short-circuits so G, which can be non-numeric when a=0, is never referenced) -- the
    same identity MODE A calls contribution_margin and BEP calls contribution_margin_per_unit
    (the cross-mode CM-parity precedent already documented on build_bep_formulas /
    build_scenario_compare_column_formulas). `extra_unknown_refs` lets a raw literal-input
    caller (BEP's own sheets) also guard varfixed/ratenet/rategross for blank; Scenario
    Compare's formula-cell inputs never need this (those refs are always base/eff cells that
    already resolve to a number, or are caught by `unknown_num(direct)` itself)."""
    unknown_terms = ",".join([unknown_num(direct), *(unknown_num(r) for r in extra_unknown_refs)])
    return (
        f'=IFERROR('
        f'IF({n_cell}="ERROR","ERROR",'
        f'IF(OR(NOT(ISNUMBER({n_cell})),{unknown_terms}),"UNKNOWN",'
        f'IF({rategross}>0,'
        f'IF({g_cell}="ERROR","ERROR",IF(NOT(ISNUMBER({g_cell})),"UNKNOWN",'
        f'{n_cell}-{direct}-{varfixed}-{ratenet}*{n_cell}-{rategross}*{g_cell})),'
        f'{n_cell}-{direct}-{varfixed}-{ratenet}*{n_cell}'
        f'))),"ERROR")'
    )


def _module_status_formula(error_refs, not_applicable_exempt_refs=None):
    """Shared 3-tier module-status rollup: ERROR if any of `error_refs` literally equals
    "ERROR"; else UNKNOWN if any of them is not a number; else OK (SPEC.md's per-mode
    ERROR > UNKNOWN > OK rollup, reused identically for Scenario Compare's own mode_a_status /
    mode_b_status / mode_c_status / bep_status cells). A ref listed in
    `not_applicable_exempt_refs` is allowed to hold the literal text "NOT_APPLICABLE" without
    counting as UNKNOWN -- BEP's own deliberate exception (an undefined break-even quantity is a
    valid OK-tier result, not a missing-data problem), which none of the other three module
    statuses need."""
    exempt = set(not_applicable_exempt_refs or ())
    error_terms = ",".join(f'{r}="ERROR"' for r in error_refs)
    unknown_terms = ",".join(
        f'AND(NOT(ISNUMBER({r})),{r}<>"NOT_APPLICABLE")' if r in exempt else f'NOT(ISNUMBER({r}))'
        for r in error_refs
    )
    return f'=IF(OR({error_terms}),"ERROR",IF(OR({unknown_terms}),"UNKNOWN","OK"))'


def _delta_precedence_formula(own_cell, baseline_cell, baseline_idx_cell):
    """Shared delta-status-propagation formula: ERROR > UNKNOWN > NOT_APPLICABLE > OK across the
    two operand cells (SPEC.md section 13/14's precedence rule), with the request-level "baseline
    column not found" case (`baseline_idx_cell=0`) forcing ERROR before either operand is even
    read. Identical on both 10_SCENARIO_COMPARE (interactive) and 11_SCENARIO_COMPARE_PARITY --
    the only two callers -- so this is the exact same formula string, not a variant."""
    return (
        f'=IF({baseline_idx_cell}=0,"ERROR",'
        f'IF(OR({own_cell}="ERROR",{baseline_cell}="ERROR"),"ERROR",'
        f'IF(OR({own_cell}="UNKNOWN",{baseline_cell}="UNKNOWN"),"UNKNOWN",'
        f'IF(OR({own_cell}="NOT_APPLICABLE",{baseline_cell}="NOT_APPLICABLE"),"NOT_APPLICABLE",'
        f'{own_cell}-{baseline_cell}))))'
    )


def _guarded_subtract_formula(left_ref, right_ref):
    """Shared 2-operand guarded subtraction: ERROR if either operand is literally "ERROR"; else
    UNKNOWN if either is not a number; else left-right. Used for direct_cost_gap
    (= allowable_direct_cost - actual_direct_cost, docs/features/mode_c_allowable_cost/SPEC.md),
    identical whether the caller is MODE C's own raw-input sheet or Scenario Compare's
    formula-cell inputs -- both operands here are already-evaluated formula cells in either
    context, so no raw-blank-vs-sentinel guard distinction applies (unlike _price_basis_formulas/
    _cmu_formula, which do need that distinction)."""
    return (
        f'=IFERROR(IF(OR({left_ref}="ERROR",{right_ref}="ERROR"),"ERROR",'
        f'IF(OR(NOT(ISNUMBER({left_ref})),NOT(ISNUMBER({right_ref}))),"UNKNOWN",'
        f'{left_ref}-{right_ref})),"ERROR")'
    )


def build_mode_c_formulas(ws, cell_map, refs):
    """Writes MODE C's formula chain (docs/features/mode_c_allowable_cost/SPEC.md /
    core/engine/modes/mode_c.py) into `ws` at the (row, col) positions given per key in
    `cell_map`, using the input cell references in `refs` (p, incvat, v, t, f, b, a, actual, vcs,
    dcs — see SPEC.md for symbol meanings). Returns {metric_key: cell_coordinate} for the 7
    official MODE C output metrics. Shared by 06_MODE_C_SIMULATOR and 07_MODE_C_PARITY_TEST so
    both use the exact same formula strings.

    `cell_map` must provide positions for the 7 official metric keys (METRIC_KEYS_C) PLUS 4
    internal helper keys: "_t_eff", "_f_eff", "_b_eff", "_a_eff".

    Every cell holds either a number or one of the text strings "UNKNOWN"/"ERROR" (raw Excel
    errors are never surfaced). ERROR conditions (SPEC.md section 7/9): t<0 or t>=1,
    vcs="invalid" (F/b/a all become ERROR). UNKNOWN conditions: N/G/t/F/b/a blank or vcs=
    "unresolved"; actual_direct_cost blank or dcs="unresolved"/"invalid"(->ERROR).

    `refs["vcs"]` ("Variable Cost Allocation Status") stands in for the shared-cost-allocation
    status a real Client Input would carry on its F/b/a variable_selling_delivery items
    (dependency_rules.md section 4) — "none" behaves like the item was entered directly;
    "unresolved" forces F/b/a (and everything downstream: allowable_direct_cost, direct_cost_gap,
    expected_contribution_margin(_rate)) to UNKNOWN; "invalid" forces them to ERROR. It is NOT a
    field in client_input.schema.json.

    `refs["dcs"]` ("Direct Cost Allocation Status") is the SEPARATE control for
    actual_direct_cost's shared-allocation status — critical dependency-isolation distinction
    (SPEC.md section 9 / dependency_rules.md section 6): dcs affects ONLY actual_direct_cost and
    direct_cost_gap. It must NEVER affect allowable_direct_cost, expected_contribution_margin, or
    expected_contribution_margin_rate — those three read only vcs (via F/b/a) and the market
    price/target-rate inputs, never actual_direct_cost at all. This is the most important Excel
    test in this sheet: setting dcs to "unresolved"/"invalid" while vcs="none" must leave ADC/CM/
    CMR completely unchanged and numeric.

    expected_contribution_margin is deliberately NOT "= t * N" — it is independently recomputed
    from the actual cost identity (CM = N - ADC - F - b*N - a*G), so an arithmetic error in the
    ADC derivation itself would not be masked by circularity (same self-check discipline as
    build_mode_b_formulas).
    """
    p, incvat, v, t, f, b, a, actual, vcs, dcs = (
        refs["p"], refs["incvat"], refs["v"], refs["t"], refs["f"], refs["b"], refs["a"],
        refs["actual"], refs["vcs"], refs["dcs"],
    )

    def put(key, formula):
        row, col = cell_map[key]
        return ws.cell(row=row, column=col, value=formula).coordinate

    n_formula, g_formula = _price_basis_formulas(p, incvat, v, _unknown_blank, _unknown_blank)
    n_cell = put("market_net_sales_ex_vat", n_formula)
    g_cell = put("market_gross_payment_incl_vat", g_formula)

    t_eff_formula = f'=IFERROR(IF(ISBLANK({t}),"UNKNOWN",IF(OR({t}<0,{t}>=1),"ERROR",{t})),"ERROR")'
    t_eff_cell = put("_t_eff", t_eff_formula)

    def alloc_formula(status_ref, value_ref):
        return (
            f'=IFERROR(IF({status_ref}="invalid","ERROR",'
            f'IF({status_ref}="unresolved","UNKNOWN",'
            f'IF(ISBLANK({value_ref}),"UNKNOWN",{value_ref}))),"ERROR")'
        )

    f_eff_cell = put("_f_eff", alloc_formula(vcs, f))
    b_eff_cell = put("_b_eff", alloc_formula(vcs, b))
    a_eff_cell = put("_a_eff", alloc_formula(vcs, a))

    # allowable_direct_cost = N(1-t-b) - aG - F ; a=0 short-circuits so G is never referenced
    # (avoids a raw #VALUE! from 0*"UNKNOWN"/0*"ERROR" when a=0 and G happens to be non-numeric).
    adc_formula = (
        f'=IFERROR('
        f'IF(OR({n_cell}="ERROR",{t_eff_cell}="ERROR",{f_eff_cell}="ERROR",{b_eff_cell}="ERROR",{a_eff_cell}="ERROR"),"ERROR",'
        f'IF(OR(NOT(ISNUMBER({n_cell})),NOT(ISNUMBER({t_eff_cell})),NOT(ISNUMBER({f_eff_cell})),'
        f'NOT(ISNUMBER({b_eff_cell})),NOT(ISNUMBER({a_eff_cell}))),"UNKNOWN",'
        f'IF({a_eff_cell}>0,'
        f'IF({g_cell}="ERROR","ERROR",IF(NOT(ISNUMBER({g_cell})),"UNKNOWN",'
        f'{n_cell}*(1-{t_eff_cell}-{b_eff_cell})-{a_eff_cell}*{g_cell}-{f_eff_cell})),'
        f'{n_cell}*(1-{t_eff_cell}-{b_eff_cell})-{f_eff_cell}'
        f'))),"ERROR")'
    )
    adc_cell = put("allowable_direct_cost", adc_formula)

    # actual_direct_cost: completely independent input path (dcs), never referenced by adc_formula
    # above — this separation IS the dependency-isolation test.
    actual_formula = alloc_formula(dcs, actual)
    actual_cell = put("actual_direct_cost", actual_formula)

    gap_formula = _guarded_subtract_formula(adc_cell, actual_cell)
    gap_cell = put("direct_cost_gap", gap_formula)

    # CM = N - ADC - F - b*N - a*G (independent self-check, NOT t*N — see docstring).
    cm_formula = (
        f'=IFERROR(IF({adc_cell}="ERROR","ERROR",IF(NOT(ISNUMBER({adc_cell})),"UNKNOWN",'
        f'IF({a_eff_cell}>0,'
        f'{n_cell}-{adc_cell}-{f_eff_cell}-{b_eff_cell}*{n_cell}-{a_eff_cell}*{g_cell},'
        f'{n_cell}-{adc_cell}-{f_eff_cell}-{b_eff_cell}*{n_cell}'
        f'))),"ERROR")'
    )
    cm_cell = put("expected_contribution_margin", cm_formula)

    # N=0 -> ERROR (confirmed-zero market price makes the rate mathematically undefined), not UNKNOWN.
    cmr_formula = (
        f'=IFERROR(IF({cm_cell}="ERROR","ERROR",IF(NOT(ISNUMBER({cm_cell})),"UNKNOWN",'
        f'IF({n_cell}=0,"ERROR",{cm_cell}/{n_cell}))),"ERROR")'
    )
    cmr_cell = put("expected_contribution_margin_rate", cmr_formula)

    return {
        "market_net_sales_ex_vat": n_cell, "market_gross_payment_incl_vat": g_cell,
        "allowable_direct_cost": adc_cell, "actual_direct_cost": actual_cell,
        "direct_cost_gap": gap_cell, "expected_contribution_margin": cm_cell,
        "expected_contribution_margin_rate": cmr_cell,
    }


def build_bep_formulas(ws, cell_map, refs):
    """Writes BEP's formula chain (docs/features/bep/SPEC.md / core/engine/modes/bep.py) into
    `ws` at the (row, col) positions given per key in `cell_map`, using the input cell references
    in `refs` (p, incvat, v, direct, varfixed, ratenet, rategross, fc, fcbasis, fcs — see SPEC.md
    for symbol meanings; `cc` and `fbc` are OPTIONAL parity-only controls, see below). Returns
    {metric_key: cell_coordinate} for the 3 official BEP output metrics plus
    "analysis_period_basis" and "_diagnostic_code" (a QA-only priority-ordered warning-code
    diagnostic, not a schema field).

    CMu = N - direct - varfixed - b*N - a*G (a=0 short-circuits so G is never referenced, same
    discipline as MODE C's ADC). CMu/FC use the exact same per-metric VAT dependency and no-item/
    null/explicit-zero rules already established for MODE A/B/C — no new business rule is
    introduced by this Excel layer (docs/features/bep/SPEC.md section 4/7).

    `refs["fcs"]` ("Fixed Cost Allocation Status" — none/component/unresolved/blended_only/
    invalid_direct) is an Excel-only simulation control standing in for the shared-cost-
    allocation status a real Client Input would carry on its fixed_operating_cost item(s)
    (dependency_rules.md section 7): "none" = no fixed-cost item at all (confirmed FC=0,
    analysis_period_basis=blank); "component" = use the `fc`/`fcbasis` input cells directly;
    "unresolved" = UNKNOWN (UNSUPPORTED_SHARED_COST_ALLOCATION); "blended_only" = UNKNOWN
    (FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED — BEP's deliberate deviation from every other mode's
    "excluded" treatment, SPEC.md section 12); "invalid_direct" = ERROR
    (INVALID_ALLOCATION_CONFIGURATION). It is NOT a field in client_input.schema.json.

    `refs["fbc"]` ("Fixed Cost Basis Consistency" — consistent/inconsistent) is a SEPARATE
    Excel-only control simulating multiple fixed_operating_cost items with disagreeing `basis`
    values (SPEC.md section 4/12's INCONSISTENT_FIXED_COST_BASIS rule) — the flat single-fc-input
    Excel model has only one basis input, so this flag is how the parity sheet exercises that
    ERROR path without an itemized cost list. Only meaningful when fcs="component"; defaults to
    "consistent" (no effect) everywhere else. Also not a schema field.

    `refs["cc"]` ("Component Count" — 1/2+) is the multi-component hard-gate control (SPEC.md
    section 11 / dependency_rules.md section 7): when > 1, ALL THREE core metrics collapse to
    "ERROR" unconditionally, before any fixed-cost/CM/currency/shared-allocation evaluation is
    even referenced — mirrors bep.py's run_bep() STEP 1 gate running strictly before STEP 2.
    Optional: 06_BEP_SIMULATOR omits it entirely (inherently single-component, no multi-component
    input structure needed there per SPEC.md section 10); only 09_BEP_PARITY_TEST supplies it.
    """
    p, incvat, v, direct, varfixed, ratenet, rategross, fc, fcbasis, fcs = (
        refs["p"], refs["incvat"], refs["v"], refs["direct"], refs["varfixed"],
        refs["ratenet"], refs["rategross"], refs["fc"], refs["fcbasis"], refs["fcs"],
    )
    fbc = refs.get("fbc")
    cc = refs.get("cc")

    def put(key, formula):
        row, col = cell_map[key]
        return ws.cell(row=row, column=col, value=formula).coordinate

    n_formula, g_formula = _price_basis_formulas(p, incvat, v, _unknown_blank, _unknown_blank)
    n_cell = put("_n", n_formula)
    g_cell = put("_g", g_formula)

    # CMu = N - direct - varfixed - b*N - a*G ; a=0 short-circuits so G is never referenced.
    cmu_formula = _cmu_formula(
        n_cell, direct, varfixed, ratenet, rategross, g_cell, _unknown_blank,
        extra_unknown_refs=(varfixed, ratenet, rategross),
    )
    cmu_cell = put("contribution_margin_per_unit", cmu_formula)

    # fixed_operating_cost via the Fixed Cost Allocation Status + Basis Consistency controls.
    fbc_check = f'{fbc}="inconsistent"' if fbc else "FALSE"
    fc_formula = (
        f'=IFERROR('
        f'IF({fcs}="invalid_direct","ERROR",'
        f'IF({fbc_check},"ERROR",'
        f'IF({fcs}="none",0,'
        f'IF(OR({fcs}="unresolved",{fcs}="blended_only"),"UNKNOWN",'
        f'IF(ISBLANK({fc}),"UNKNOWN",'
        f'IF({fc}<0,"ERROR",{fc})))))),'
        f'"ERROR")'
    )
    fc_cell = put("fixed_operating_cost", fc_formula)

    basis_formula = (
        f'=IF(OR({fcs}="invalid_direct",{fbc_check}),"",'
        f'IF({fcs}="none","",'
        f'IF(OR({fcs}="unresolved",{fcs}="blended_only"),"",'
        f'IF(ISBLANK({fc}),"",'
        f'IF({fc}<0,"",{fcbasis})))))'
    )
    basis_cell = put("analysis_period_basis", basis_formula)

    # break_even_quantity_exact: ERROR > UNKNOWN > (CMu<=0 -> NOT_APPLICABLE) > OK division.
    # 0 is a valid output ONLY for FC=0,CMu>0 — never for any CMu<=0 combination (SPEC.md section 9).
    q_formula = (
        f'=IFERROR('
        f'IF(OR({cmu_cell}="ERROR",{fc_cell}="ERROR"),"ERROR",'
        f'IF(OR(NOT(ISNUMBER({cmu_cell})),NOT(ISNUMBER({fc_cell}))),"UNKNOWN",'
        f'IF({cmu_cell}<=0,"NOT_APPLICABLE",'
        f'{fc_cell}/{cmu_cell}))),'
        f'"ERROR")'
    )
    q_cell = put("break_even_quantity_exact", q_formula)

    # Diagnostic warning-code cell (QA-only, not a schema field) — priority mirrors bep.py exactly.
    diag_formula = (
        f'=IF({cc}>1,"MULTI_COMPONENT_BEP_NOT_SUPPORTED",'
        if cc else '=IF(FALSE,"",'
    ) + (
        f'IF({fcs}="invalid_direct","INVALID_ALLOCATION_CONFIGURATION",'
        f'IF({fbc_check},"INCONSISTENT_FIXED_COST_BASIS",'
        f'IF(AND({fcs}="component",NOT(ISBLANK({fc})),{fc}<0),"INVALID_NEGATIVE_COST",'
        f'IF({cmu_cell}="ERROR","CALCULATION_ERROR",'
        f'IF({fcs}="blended_only","FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED",'
        f'IF({fcs}="unresolved","UNSUPPORTED_SHARED_COST_ALLOCATION",'
        f'IF(NOT(ISNUMBER({cmu_cell})),"MISSING_DEPENDENCY",'
        f'IF(AND({fcs}="component",ISBLANK({fc})),"MISSING_DEPENDENCY",'
        f'IF(AND({cmu_cell}=0,{fc_cell}=0),"BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST",'
        f'IF({cmu_cell}=0,"BREAK_EVEN_UNDEFINED_ZERO_MARGIN",'
        f'IF({cmu_cell}<0,"BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN",'
        f'"NONE"))))))))))))'
    )
    diag_cell = put("_diagnostic_code", diag_formula)

    if cc:
        # Now apply the multi-component override to the 3 core cells by rewriting them in place
        # with an outer wrapper — done last so the formulas above (needed by the diagnostic cell
        # too) are already in their final referenced positions.
        for key, formula_no_cc in (
            ("contribution_margin_per_unit", cmu_formula),
            ("fixed_operating_cost", fc_formula),
            ("break_even_quantity_exact", q_formula),
        ):
            row, col = cell_map[key]
            wrapped = f'=IF({cc}>1,"ERROR",{formula_no_cc[1:]})'
            ws.cell(row=row, column=col, value=wrapped)
        row, col = cell_map["analysis_period_basis"]
        ws.cell(row=row, column=col, value=f'=IF({cc}>1,"",{basis_formula[1:]})')

    return {
        "contribution_margin_per_unit": cmu_cell, "fixed_operating_cost": fc_cell,
        "break_even_quantity_exact": q_cell, "analysis_period_basis": basis_cell,
        "_diagnostic_code": diag_cell,
    }


def build_scenario_compare_column_formulas(ws, col, row_map, base_refs, override_refs, validity_ref=None):
    """Writes ONE scenario column's full formula chain (docs/features/scenario_compare/SPEC.md /
    core/engine/scenario_compare.py) — effective inputs, then MODE A/B/C/BEP formula chains
    reusing the exact same math as build_mode_b_formulas/build_mode_c_formulas/
    build_bep_formulas, and a scenario-level status rollup. Writes into column `col` at the rows
    named in `row_map` (shared across every scenario column on the sheet, so metric rows line up
    for the delta section's cross-column INDEX/MATCH lookups).

    `base_refs`: single-cell refs shared by every scenario (never overridden in Excel v0.1):
        p, incvat, v, tmp, disc, tcm  -- component/target fields (ALSO the fallback "inherit"
        source for each overridable field, since base_refs IS the base row)
        direct, fc -- the two representative cost-item override slots' base values
        varfixed, ratenet, rategross -- NOT overridable in this workbook (SPEC.md section 6's
        "representative slot" simplification): plain references, always the base value.

    `override_refs`: per-field {"mode": cellref, "value": cellref} for exactly the SPEC.md
    section 4 allowlist fields this workbook exposes an override slot for: p, incvat, v, tmp,
    disc, tcm, direct, fc. mode in {"inherit","null","value"} (Excel-only representation of
    Python's omitted-vs-explicit-null distinction, SPEC.md section 5/7 -- "inherit"=omitted,
    "null"=explicit null/UNKNOWN, "value"=the override value cell).

    Every result cell holds a number or one of the literal strings "UNKNOWN"/"ERROR"/
    "NOT_APPLICABLE" -- exact string equality is used throughout (not ISNUMBER guessing) because
    every formula in this chain guarantees one of those three sentinels or a number, never a raw
    Excel error.

    `validity_ref` (parity-sheet only, Excel-only simulation control, NOT a schema field):
    optional cell whose value "invalid" simulates this scenario's merged client_input failing
    STEP 3 schema validation (docs/features/scenario_compare/SPEC.md section 7/14a) -- every
    mode status and the scenario status collapse to "ERROR" and no metric cell exposes a
    meaningful value. When a scenario using this baseline is compared, its own metric cells
    literally read "ERROR", so the delta section's status propagation (section 14) picks that up
    automatically -- no separate "is this the invalid baseline" detection is needed downstream.
    """
    p, incvat, v, tmp, disc, tcm = (
        base_refs["p"], base_refs["incvat"], base_refs["v"], base_refs["tmp"],
        base_refs["disc"], base_refs["tcm"],
    )
    varfixed, ratenet = base_refs["varfixed"], base_refs["ratenet"]

    def put(key, formula):
        row = row_map[key]
        return ws.cell(row=row, column=col, value=formula).coordinate

    def eff(field, base_ref):
        o = override_refs[field]
        formula = f'=IF({o["mode"]}="inherit",{base_ref},IF({o["mode"]}="null","UNKNOWN",{o["value"]}))'
        return put(f"eff_{field}", formula)

    eff_p = eff("p", p)
    eff_incvat = eff("incvat", incvat)
    eff_v = eff("v", v)
    eff_tmp = eff("tmp", tmp)
    eff_disc = eff("disc", disc)
    eff_tcm = eff("tcm", tcm)
    eff_direct = eff("direct", base_refs["direct"])
    eff_fc = eff("fc", base_refs["fc"])
    # gross-payment fee rate (a) is overridable ONLY where the caller supplies an override slot
    # for it (the 09_SCENARIO_COMPARE_PARITY sheet's "fee increase" cases) -- the interactive
    # 10_SCENARIO_COMPARE sheet does not expose this slot (representative-slot simplification,
    # SPEC.md section 6), so it falls back to a plain, non-overridable reference there, exactly
    # like net_sales fee rate (b) always does.
    rategross = eff("rategross", base_refs["rategross"]) if "rategross" in override_refs else base_refs["rategross"]

    # --- MODE A / BEP shared price basis (N, G) from actual price ---
    n_formula, g_formula = _price_basis_formulas(
        eff_p, eff_incvat, eff_v, _unknown_num_sentinel, _unknown_bool_sentinel,
    )
    n_cell = put("n", n_formula)
    g_cell = put("g", g_formula)

    # --- CMu = contribution_margin_per_unit (MODE A's contribution_margin, BEP's CMu -- same
    #     cell serves both, per the cross-mode CM-parity precedent) ---
    cmu_formula = _cmu_formula(
        n_cell, eff_direct, varfixed, ratenet, rategross, g_cell, _unknown_num_sentinel,
    )
    cmu_cell = put("cmu", cmu_formula)

    cmr_formula = (
        f'=IFERROR(IF({cmu_cell}="ERROR","ERROR",IF(NOT(ISNUMBER({cmu_cell})),"UNKNOWN",'
        f'IF({n_cell}=0,"ERROR",{cmu_cell}/{n_cell}))),"ERROR")'
    )
    cmr_cell = put("cmr", cmr_formula)

    mode_a_status_formula = _module_status_formula([n_cell, cmu_cell, cmr_cell])
    mode_a_status_cell = put("mode_a_status", mode_a_status_formula)

    # --- MODE B: C = direct + fixed-amount variable; D; N/G/S/L ---
    c_b_formula = f'=IFERROR(IF(NOT(ISNUMBER({eff_direct})),{eff_direct},{eff_direct}+{varfixed}),"ERROR")'
    c_b_cell = put("c_b", c_b_formula)

    d_b_formula = (
        f'=IFERROR(IF(NOT(ISNUMBER({eff_tcm})),"UNKNOWN",'
        f'IF(OR({eff_tcm}<0,{eff_tcm}>=1),"ERROR",'
        f'IF({rategross}=0,'
        f'IF(1-{eff_tcm}-{ratenet}<=0,"ERROR",1-{eff_tcm}-{ratenet}),'
        f'IF(NOT(ISNUMBER({eff_v})),"UNKNOWN",'
        f'IF(1-{eff_tcm}-{ratenet}-{rategross}*(1+{eff_v})<=0,"ERROR",1-{eff_tcm}-{ratenet}-{rategross}*(1+{eff_v})))))),"ERROR")'
    )
    d_b_cell = put("d_b", d_b_formula)

    n_b_formula = f'=IFERROR(IF(NOT(ISNUMBER({c_b_cell})),{c_b_cell},IF(NOT(ISNUMBER({d_b_cell})),{d_b_cell},{c_b_cell}/{d_b_cell})),"ERROR")'
    n_b_cell = put("n_b", n_b_formula)

    g_b_formula = f'=IFERROR(IF(NOT(ISNUMBER({n_b_cell})),{n_b_cell},IF(NOT(ISNUMBER({eff_v})),"UNKNOWN",{n_b_cell}*(1+{eff_v}))),"ERROR")'
    g_b_cell = put("g_b", g_b_formula)

    s_b_formula = f'=IFERROR(IF({eff_incvat}="UNKNOWN","UNKNOWN",IF({eff_incvat}=FALSE,{n_b_cell},{g_b_cell})),"ERROR")'
    s_b_cell = put("s_b", s_b_formula)

    l_b_formula = (
        f'=IFERROR(IF(NOT(ISNUMBER({s_b_cell})),{s_b_cell},'
        f'IF(NOT(ISNUMBER({eff_disc})),"UNKNOWN",'
        f'IF(OR({eff_disc}<0,{eff_disc}>=1),"ERROR",'
        f'IF({eff_disc}=0,{s_b_cell},{s_b_cell}/(1-{eff_disc}))))),"ERROR")'
    )
    l_b_cell = put("l_b", l_b_formula)

    mode_b_status_formula = _module_status_formula([s_b_cell, l_b_cell])
    mode_b_status_cell = put("mode_b_status", mode_b_status_formula)

    # --- MODE C: Nc/Gc from target_market_price; ADC; actual (reuses eff_direct); gap ---
    nc_formula, gc_formula = _price_basis_formulas(
        eff_tmp, eff_incvat, eff_v, _unknown_num_sentinel, _unknown_bool_sentinel,
    )
    nc_cell = put("nc", nc_formula)
    gc_cell = put("gc", gc_formula)

    adc_formula = (
        f'=IFERROR('
        f'IF({nc_cell}="ERROR","ERROR",'
        f'IF(NOT(ISNUMBER({eff_tcm})),"UNKNOWN",'
        f'IF(OR({eff_tcm}<0,{eff_tcm}>=1),"ERROR",'
        f'IF(NOT(ISNUMBER({nc_cell})),"UNKNOWN",'
        f'IF({rategross}>0,'
        f'IF({gc_cell}="ERROR","ERROR",IF(NOT(ISNUMBER({gc_cell})),"UNKNOWN",'
        f'{nc_cell}*(1-{eff_tcm}-{ratenet})-{rategross}*{gc_cell}-{varfixed})),'
        f'{nc_cell}*(1-{eff_tcm}-{ratenet})-{varfixed}'
        f'))))),"ERROR")'
    )
    adc_cell = put("adc", adc_formula)

    gap_formula = _guarded_subtract_formula(adc_cell, eff_direct)
    gap_cell = put("gap", gap_formula)

    mode_c_status_formula = _module_status_formula([adc_cell, eff_direct, gap_cell])
    mode_c_status_cell = put("mode_c_status", mode_c_status_formula)

    # --- BEP: fixed_operating_cost (from eff_fc), Q_BEP = FC/CMu ---
    fc_formula = f'=IFERROR(IF(NOT(ISNUMBER({eff_fc})),{eff_fc},IF({eff_fc}<0,"ERROR",{eff_fc})),"ERROR")'
    fc_cell = put("fc_result", fc_formula)

    q_formula = (
        f'=IFERROR('
        f'IF(OR({cmu_cell}="ERROR",{fc_cell}="ERROR"),"ERROR",'
        f'IF(OR(NOT(ISNUMBER({cmu_cell})),NOT(ISNUMBER({fc_cell}))),"UNKNOWN",'
        f'IF({cmu_cell}<=0,"NOT_APPLICABLE",'
        f'{fc_cell}/{cmu_cell}))),'
        f'"ERROR")'
    )
    q_cell = put("q_bep", q_formula)

    bep_status_formula = _module_status_formula(
        [cmu_cell, fc_cell, q_cell], not_applicable_exempt_refs=[q_cell],
    )
    bep_status_cell = put("bep_status", bep_status_formula)

    scenario_status_formula = (
        f'=IF(OR({mode_a_status_cell}="ERROR",{mode_b_status_cell}="ERROR",{mode_c_status_cell}="ERROR",{bep_status_cell}="ERROR"),"ERROR",'
        f'IF(OR({mode_a_status_cell}="UNKNOWN",{mode_b_status_cell}="UNKNOWN",{mode_c_status_cell}="UNKNOWN",{bep_status_cell}="UNKNOWN"),"INCOMPLETE","OK"))'
    )
    scenario_status_cell = put("scenario_status", scenario_status_formula)

    result = {
        "eff_p": eff_p, "eff_incvat": eff_incvat, "eff_v": eff_v, "eff_tmp": eff_tmp,
        "eff_disc": eff_disc, "eff_tcm": eff_tcm, "eff_direct": eff_direct, "eff_fc": eff_fc,
        "n": n_cell, "g": g_cell, "cmu": cmu_cell, "cmr": cmr_cell, "mode_a_status": mode_a_status_cell,
        "c_b": c_b_cell, "d_b": d_b_cell, "n_b": n_b_cell, "g_b": g_b_cell, "s_b": s_b_cell,
        "l_b": l_b_cell, "mode_b_status": mode_b_status_cell,
        "nc": nc_cell, "gc": gc_cell, "adc": adc_cell, "gap": gap_cell, "mode_c_status": mode_c_status_cell,
        "fc_result": fc_cell, "q_bep": q_cell, "bep_status": bep_status_cell,
        "scenario_status": scenario_status_cell,
    }

    if validity_ref:
        # Parity-sheet-only Excel simulation control: "invalid" forces every status/metric this
        # scenario exposes to ERROR, simulating a STEP 3 schema-validation failure -- done as a
        # post-hoc overwrite of each cell's OWN original formula text (captured below BEFORE
        # overwriting, since the cell's own coordinate cannot appear inside its own replacement
        # formula -- that would self-reference/circular-ref the cell, same pitfall as the BEP
        # analysis_period_basis bug from an earlier phase). Only the STATUS/RESULT cells that
        # matter for downstream delta/status propagation are wrapped, not every intermediate
        # helper cell (eff_*, g, d_b, n_b, g_b, nc, gc stay as plain "valid" arithmetic -- they
        # simply become irrelevant once the cells that read them are overwritten).
        original_formulas = {
            "mode_a_status": mode_a_status_formula, "mode_b_status": mode_b_status_formula,
            "mode_c_status": mode_c_status_formula, "bep_status": bep_status_formula,
            "scenario_status": scenario_status_formula,
            "n": n_formula, "cmu": cmu_formula, "cmr": cmr_formula,
            "s_b": s_b_formula, "l_b": l_b_formula, "adc": adc_formula, "gap": gap_formula,
            "fc_result": fc_formula, "q_bep": q_formula,
        }
        for key, original_formula in original_formulas.items():
            row = row_map[key]
            wrapped = f'=IF({validity_ref}="invalid","ERROR",{original_formula[1:]})'
            ws.cell(row=row, column=col, value=wrapped)

    return result


wb = openpyxl.Workbook()

# ================================================================
# SHEET: 00_GUIDE
# ================================================================
g = wb.active
g.title = "00_GUIDE"
g.sheet_view.showGridLines = False
g.column_dimensions["A"].width = 2
g.column_dimensions["B"].width = 100

r = 2
title_row(g, r, "MODE A + MODE B + MODE C + BEP + Scenario Compare Excel Simulator — Pricing Harness", span=1); r += 2

section_row(g, r, "Source of Truth 구조 (반드시 지켜야 하는 원칙)", span=1); r += 1
guide_lines = [
    "A. Formula Source of Truth = docs/features/mode_a_current_price/SPEC.md (MODE A), docs/features/mode_b_target_price/SPEC.md (MODE B), docs/features/mode_c_allowable_cost/SPEC.md (MODE C), docs/features/bep/SPEC.md (BEP) — 계산식의 공식 기준.",
    "B. Reference Implementation = core/engine/modes/mode_a.py, core/engine/modes/mode_b.py, core/engine/modes/mode_c.py, core/engine/modes/bep.py (Python), core/engine/economics.py(MODE A/BEP가 공유하는 Contribution Margin economic primitive — 실제 shared-cost 배부 엔진이 아님) — SPEC을 구현/테스트하는 기준 엔진. tests/test_mode_a.py 13/13, tests/test_mode_b.py 24/24, tests/test_mode_c.py 26/26, tests/test_bep.py 32/32 PASS.",
    "C. Interactive Simulation Layer = 이 Excel 파일 — 사용자가 값을 바꿔가며 결과 변화를 체감하는 도구. 수식은 반드시 A/B와 동일한 논리를 따른다. Excel은 독립적인 계산 엔진이 아니며, Python과 다른 계산 규칙을 만들지 않는다.",
    "D. Official Result Source = analysis_result.json (core/schemas/analysis_result.schema.json) — 실제 컨설팅 판단에 쓰는 공식 결과. Dashboard/Report/Quotation은 이 파일만 읽고, Excel 셀을 재계산하거나 직접 읽지 않는다.",
]
for line in guide_lines:
    g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
    c = g.cell(row=r, column=2, value=line)
    c.font = label_font
    c.alignment = Alignment(wrap_text=True, vertical="top")
    g.row_dimensions[r].height = 32
    r += 1
r += 1

section_row(g, r, "blank ≠ 0 원칙", span=1); r += 1
g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
c = g.cell(row=r, column=2, value=(
    "필수 입력이 비어 있으면 그 값에 의존하는 결과는 0이 아니라 \"미입력\" 또는 \"계산불가\"로 표시됩니다. "
    "#DIV/0!, #VALUE!, #N/A 같은 Excel 기본 오류가 사용자 화면에 그대로 노출되지 않도록 모든 계산 셀은 IFERROR로 감쌌습니다."
))
c.font = label_font
c.alignment = Alignment(wrap_text=True, vertical="top")
g.row_dimensions[r].height = 40
r += 2

section_row(g, r, "이번 버전(v0.5)이 완전히 지원하는 범위", span=1); r += 1
scope_lines = [
    "01_SIMULATOR(MODE A)는 단일 컴포넌트 상품(simple one-time product, ecommerce product)만 대화형으로 지원합니다.",
    "03_PARITY_TEST(MODE A)에서 두 시나리오(simple / ecommerce) 모두 Python 엔진 결과와 대조 검증되어 있습니다.",
    "04_MODE_B_SIMULATOR는 단일 컴포넌트, shared-cost 없음 기준으로 목표가격(N/G/판매가/정가)을 대화형으로 계산합니다 — C/b/a는 이미 합산된 값을 입력합니다(01_SIMULATOR와 동일한 단순화).",
    "05_MODE_B_PARITY_TEST에서 15개 시나리오 전부 Excel 실시간 재계산 vs Python 엔진으로 대조 검증되어 있습니다. Shared-cost 시나리오 2개(#14,#15)는 실제 배부(allocation) 금액을 계산하지는 않지만, Shared Cost Status 플래그로 UNKNOWN/ERROR를 정확히 산출하는지 실시간 대조합니다 — 아래 'Shared Cost' 항목 참고.",
    "06_MODE_C_SIMULATOR는 단일 컴포넌트 기준으로 시장가격(target_market_price)과 목표 CM율로부터 허용원가(ADC)를 대화형으로 계산합니다 — F/b/a/실제직접원가는 이미 합산된 값을 입력합니다(04_MODE_B_SIMULATOR와 동일한 단순화). Variable Cost Allocation Status와 Direct Cost Allocation Status, 2개의 독립된 Excel-only 컨트롤을 사용합니다.",
    "07_MODE_C_PARITY_TEST에서 CASE.md TC1-20 전부 Excel 실시간 재계산 vs Python 엔진으로 대조 검증되어 있습니다 — 특히 TC19/TC20은 Direct Cost Allocation Status를 UNKNOWN으로 바꿔도 allowable_direct_cost/expected_contribution_margin(_rate)이 전혀 영향받지 않는지(dependency isolation)를 실시간으로 검증합니다.",
    "08_BEP_SIMULATOR는 단일 컴포넌트 기준으로 현재 실제가격(actual_price, MODE A와 동일한 가격 기준) + Contribution Margin + fixed_operating_cost로부터 손익분기 판매량(Q_BEP)을 대화형으로 계산합니다. Fixed Cost Allocation Status 1개의 Excel-only 컨트롤을 사용합니다.",
    "09_BEP_PARITY_TEST에서 CASE.md TC1-23 + 보강 케이스 3개(TC24-26), 총 26개 중 25개가 Excel 실시간 재계산 vs Python 엔진으로 대조 검증되어 있습니다 — TC13(통화 미지원)만 항목별 통화 입력이 없어 reference-only입니다. Q_BEP가 숫자일 때는 Self-Check(|Q_BEP×CMu−FC|≤tolerance)로 Python 값을 그대로 복사하지 않았음을 독립 검증합니다.",
    "10_SCENARIO_COMPARE는 하나의 Base Input + 최대 5개 시나리오(A~E) override로 MODE A/B/C/BEP를 "
    "각각 실행하고 결과를 나란히 비교합니다. Base + Override 방식이며, Scenario Compare 전용 계산 "
    "공식은 없습니다 — 기존 4개 모드의 formula chain을 시나리오별로 재사용/복제한 것입니다.",
    "11_SCENARIO_COMPARE_PARITY에서 CASE.md TC1-37 중 대표 24개 케이스가 Excel 실시간 재계산 vs "
    "Python 엔진(core/engine/scenario_compare.py)으로 대조 검증되어 있습니다 — baseline self-delta "
    "status 전파, invalid baseline의 sibling absolute 보존, request-level ERROR(duplicate scenario_id/"
    "baseline not found)까지 포함합니다.",
    "blank=UNKNOWN / 0=explicit zero 원칙은 MODE A, MODE B, MODE C, BEP, Scenario Compare 모두 동일하게 적용됩니다.",
]
for line in scope_lines:
    g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
    c = g.cell(row=r, column=2, value="• " + line)
    c.font = label_font
    c.alignment = Alignment(wrap_text=True, vertical="top")
    g.row_dimensions[r].height = 28
    r += 1
r += 1

section_row(g, r, "Hybrid HW+SaaS — 참고용 (이 Excel에서 직접 계산하지 않음)", span=1); r += 1
g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
c = g.cell(row=r, column=2, value=(
    "컴포넌트가 2개 이상인 하이브리드 상품은 단일-컴포넌트 Simulator 구조로 표현할 수 없어 이 Excel에서는 "
    "임의로 계산하지 않습니다. 아래는 Python Engine이 실제로 계산한 결과(core/schemas/examples/analysis_results/"
    "03_hybrid_hw_saas.analysis_result.json)를 그대로 옮긴 참고용 수치입니다 — 이 시트에서 재계산되지 않는 고정값입니다."
))
c.font = label_font
c.alignment = Alignment(wrap_text=True, vertical="top")
g.row_dimensions[r].height = 48
r += 1

hdr_row = r
for i, h in enumerate(["Component", "Gross Profit", "Gross Profit Rate", "Contribution Margin"]):
    cc = g.cell(row=r, column=2 + i, value=h)
    cc.font = header_font
    cc.fill = header_fill
    cc.alignment = Alignment(horizontal="center")
r += 1
hybrid_rows = [
    ("hardware", "181.48 USD (OK)", "54.4% (OK)", "UNKNOWN — blended.allocation[pg_fee, channel_fee, maintenance_visit] 미구현"),
    ("saas_subscription", "22.59 USD (OK)", "87.1% (OK)", "UNKNOWN — blended.allocation[pg_fee, channel_fee, maintenance_visit] 미구현"),
]
for row_vals in hybrid_rows:
    for i, v in enumerate(row_vals):
        cc = g.cell(row=r, column=2 + i, value=v)
        cc.font = label_font
        cc.border = box
        cc.alignment = Alignment(wrap_text=True, vertical="center")
    g.row_dimensions[r].height = 30
    r += 1
r += 1

# ================================================================
# MODE B shared-cost reference block — computed live from mode_b.py, same pattern as the
# Hybrid HW+SaaS block above. Kept in sync with 05_MODE_B_PARITY_TEST's #14/#15 (same
# extra_cost_items) — both sections must describe the exact same two scenarios.
# ================================================================
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from core.engine.modes.mode_b import run_mode_b as _run_mode_b_for_guide  # noqa: E402
from scenario_helpers import make_client_input_b as _make_ci_b_for_guide  # noqa: E402

_shared_unresolved_ci = _make_ci_b_for_guide(
    target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0,
    vat_rate=0.10, includes_vat=False,
    extra_cost_items=[{
        "item_id": "shared_channel_fee", "label": "공유 채널수수료", "cost_category": "variable_selling_delivery",
        "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
        "applies_to_component": "shared", "allocation_rule": "fixed_share",
    }],
)
_shared_invalid_ci = _make_ci_b_for_guide(
    target_cm_rate=0.4, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0,
    vat_rate=0.10, includes_vat=False,
    extra_cost_items=[{
        "item_id": "shared_channel_direct", "label": "모순 설정: shared + direct 수수료", "cost_category": "variable_selling_delivery",
        "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
        "applies_to_component": "shared", "allocation_rule": "direct",
    }],
)
_shared_unresolved_m = _run_mode_b_for_guide(_shared_unresolved_ci)["per_component"]["main"]
_shared_invalid_m = _run_mode_b_for_guide(_shared_invalid_ci)["per_component"]["main"]

section_row(g, r, "MODE B Shared Cost Status — Excel-only simulation control", span=1); r += 1
g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
c = g.cell(row=r, column=2, value=(
    "04_MODE_B_SIMULATOR / 05_MODE_B_PARITY_TEST의 'Shared Cost Status' (none/unresolved/invalid) "
    "입력은 client_input.schema.json의 정식 필드가 아닙니다. Shared Cost Status is an Excel "
    "simulation control only. It is not a field in client_input.schema.json. The production "
    "Python engine derives this state from actual cost item / applies_to_component / "
    "allocation_rule data (core/engine/modes/mode_b.py, dependency_rules.md §4) — never from a "
    "flag. 이 플래그는 shared 비용의 실제 배부(allocation) 금액을 계산하지 않고, 배부가 미구현/모순인 "
    "상태에서 MODE B가 UNKNOWN(unresolved) 또는 ERROR(invalid)를 정확히 산출하는지만 검증합니다 — "
    "Excel v0.2에도 실제 allocation engine은 추가되지 않았습니다. 아래는 05_MODE_B_PARITY_TEST의 "
    "#14/#15와 동일한 시나리오를 core/engine/modes/mode_b.py로 직접 실행한 결과(빌드 시점 고정값)입니다."
))
c.font = label_font
c.alignment = Alignment(wrap_text=True, vertical="top")
g.row_dimensions[r].height = 68
r += 1

hdr_row = r
for i, h in enumerate(["Scenario", "denominator", "required_net_sales_ex_vat", "Warning code"]):
    cc = g.cell(row=r, column=2 + i, value=h)
    cc.font = header_font
    cc.fill = header_fill
    cc.alignment = Alignment(horizontal="center")
r += 1


def _fmt_metric_for_guide(m):
    return f'{m["value"]:.2f} (OK)' if m["status"] == "OK" else f'{m["status"]}'


def _first_code_for_guide(result_metrics_key, ci, run_result):
    for w in run_result["warnings"]:
        if w["metric_path"].endswith(f".{result_metrics_key}"):
            return w["code"]
    return "—"


_shared_unresolved_full = _run_mode_b_for_guide(_shared_unresolved_ci)
_shared_invalid_full = _run_mode_b_for_guide(_shared_invalid_ci)
shared_ref_rows = [
    ("#14 shared + fixed_share (unresolved)",
     _fmt_metric_for_guide(_shared_unresolved_m["denominator"]),
     _fmt_metric_for_guide(_shared_unresolved_m["required_net_sales_ex_vat"]),
     _first_code_for_guide("denominator", _shared_unresolved_ci, _shared_unresolved_full)),
    ("#15 shared + direct (invalid config)",
     _fmt_metric_for_guide(_shared_invalid_m["denominator"]),
     _fmt_metric_for_guide(_shared_invalid_m["required_net_sales_ex_vat"]),
     _first_code_for_guide("denominator", _shared_invalid_ci, _shared_invalid_full)),
]
for row_vals in shared_ref_rows:
    for i, v in enumerate(row_vals):
        cc = g.cell(row=r, column=2 + i, value=v)
        cc.font = label_font
        cc.border = box
        cc.alignment = Alignment(wrap_text=True, vertical="center")
    g.row_dimensions[r].height = 30
    r += 1

section_row(g, r, "MODE C Allocation Status — Excel-only simulation controls (TWO, independent)", span=1); r += 1
g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
c = g.cell(row=r, column=2, value=(
    "06_MODE_C_SIMULATOR / 07_MODE_C_PARITY_TEST는 'Variable Cost Allocation Status'와 'Direct Cost "
    "Allocation Status', 2개의 독립된 Excel-only 컨트롤을 사용합니다 — 둘 다 client_input.schema.json의 "
    "정식 필드가 아닙니다(Excel simulation control only, not a field in client_input.schema.json). "
    "Variable Cost Allocation Status는 F/b/a(변동비)에 대한 공유비용 배부 상태를 시뮬레이션하며, "
    "unresolved/invalid일 때 allowable_direct_cost(ADC)·direct_cost_gap·expected_contribution_margin"
    "(_rate)까지 전부 UNKNOWN/ERROR로 전파됩니다. Direct Cost Allocation Status는 실제 직접원가"
    "(actual_direct_cost)에 대한 공유비용 배부 상태만 시뮬레이션하며, unresolved/invalid여도 이는 "
    "actual_direct_cost와 direct_cost_gap에만 영향을 주고 allowable_direct_cost·expected_contribution_"
    "margin(_rate)은 절대 영향받지 않습니다 — 이것이 MODE C Excel의 가장 중요한 dependency-isolation "
    "테스트입니다 (docs/features/mode_c_allowable_cost/SPEC.md §9, core/schemas/dependency_rules.md §6). "
    "07_MODE_C_PARITY_TEST의 TC19/TC20이 이 분리를 실시간으로 증명합니다."
))
c.font = label_font
c.alignment = Alignment(wrap_text=True, vertical="top")
g.row_dimensions[r].height = 96
r += 2

section_row(g, r, "BEP — Break-Even Point", span=1); r += 1
bep_guide_lines = [
    "질문: 현재 가격 + Contribution Margin + fixed operating cost → 손익분기 판매량(Q_BEP)은? "
    "BEP는 항상 현재 실제가격(actual_price, MODE A와 동일한 가격 기준) 기준으로 계산합니다 — MODE B의 "
    "required price나 MODE C의 market price를 대입하는 기능은 없습니다(향후 Scenario Compare 범위).",
    "Fixed Operating Cost Basis(예: per_month)는 quantity unit이 아니라 analysis period context입니다. "
    "break_even_quantity_exact의 unit은 항상 \"units\"이고, Fixed Operating Cost가 정의된 기간을 "
    "별도의 'Analysis Period Basis' 셀로 분리해서 보여줍니다 — 둘을 하나로 섞어 표시하지 않습니다.",
    "blank=UNKNOWN / 0=explicit zero 원칙은 BEP에도 동일하게 적용됩니다 — 단, fixed_operating_cost 항목이 "
    "'아예 없음'과 '항목은 있지만 값이 비어 있음'은 서로 다른 상태입니다(전자는 확정된 0/OK, 후자는 "
    "UNKNOWN) — Fixed Cost Allocation Status='none'으로 전자를, 'component'+금액 공백으로 후자를 표현합니다.",
    "Contribution Margin per Unit(CMu)이 0 또는 음수인 경우는 계산 오류(ERROR)가 아니라 BEP 고유의 "
    "NOT_APPLICABLE 상태입니다 — 모든 입력값이 확정되어 있지만 손익분기 판매량이라는 개념 자체가 "
    "성립하지 않는 경우이며, 0이나 음수를 Q_BEP로 표시하지 않습니다. module status는 낮아지지 않습니다.",
    "BEP v0.1은 단일 컴포넌트 상품만 지원합니다. 09_BEP_PARITY_TEST의 Component Count 컨트롤(Excel-only, "
    "schema field 아님)로 2개 이상 컴포넌트 시나리오를 시뮬레이션하면 즉시 ERROR/MULTI_COMPONENT_BEP_"
    "NOT_SUPPORTED로 처리되고, 이후 어떤 basis/CM/fixed-cost 계산도 수행되지 않습니다 — 이 gate가 다른 "
    "모든 validation보다 우선합니다.",
    "실제 shared-cost 배부(allocation) 엔진은 여전히 구현되어 있지 않습니다. Fixed Cost Allocation "
    "Status(component/unresolved/blended_only/invalid_direct)와 09_BEP_PARITY_TEST의 Fixed Cost Basis "
    "Consistency는 전부 Excel-only 시뮬레이션 컨트롤이며 client_input.schema.json의 정식 필드가 아닙니다. "
    "특히 blended_only는 다른 모드의 '배부 대상 아님 → 0으로 제외' 규칙을 그대로 쓰지 않고 UNKNOWN으로 "
    "처리합니다 — BEP의 분자가 바로 fixed_operating_cost이기 때문에, 실제 존재하는 고정비를 조용히 "
    "0으로 만드는 것을 방지하기 위한 의도적인 편차입니다(docs/features/bep/SPEC.md §12).",
]
for line in bep_guide_lines:
    g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
    c = g.cell(row=r, column=2, value="• " + line)
    c.font = label_font
    c.alignment = Alignment(wrap_text=True, vertical="top")
    g.row_dimensions[r].height = 56
    r += 1
r += 1

section_row(g, r, "Scenario Compare — orchestration layer (not a new calculation mode)", span=1); r += 1
sc_guide_lines = [
    "Scenario Compare는 새로운 가격 계산 엔진이 아니라, 기존 MODE A/B/C/BEP를 여러 가정(base + "
    "override)에 대해 반복 실행하고 그 결과를 나란히 비교하는 orchestration layer입니다. Contribution "
    "Margin/BEP/VAT normalization/cost allocation 규칙을 새로 정의하지 않으며, 모든 숫자는 4개 모드의 "
    "기존 출력을 그대로 읽어온 것입니다.",
    "Excel v0.1은 최대 5개 시나리오(A~E)로 제한됩니다 — 이는 presentation-layer 제한이며, Python Core"
    "(core/engine/scenario_compare.py)는 이 제한이 없습니다(2개 이상 임의 개수 지원).",
    "Baseline Scenario ID는 항상 명시적으로 지정해야 합니다 — 첫 번째 시나리오(컬럼 A)를 자동으로 "
    "baseline으로 취급하지 않습니다. Baseline이 활성 Scenario ID 중에 없으면 request-level ERROR입니다.",
    "Override 입력은 blank 하나로 'inherit'과 'explicit null'을 동시에 표현하지 않습니다 — 각 override "
    "필드마다 Mode(inherit/null/value) 컨트롤을 따로 둡니다. inherit=base 값 유지(Python의 omitted와 "
    "동일), null=명시적 UNKNOWN(Python의 explicit null과 동일), value=Value 셀의 입력값 사용.",
    "Scenario ID / Cost Item ID는 array position(컬럼 순서)이 아니라 명시적 식별자입니다 — 컬럼을 "
    "재배치해도 baseline 참조나 override 대상이 바뀌지 않습니다(component_id/item_id 기반 identity, "
    "index 기반 identity 금지).",
    "Scenario Compare v0.1은 structural override(component/item 추가·삭제, component_id/item_id/"
    "cost_category/basis/applies_to_component/allocation_rule 변경)를 지원하지 않습니다 — value override"
    "(amount/rate/price 등)만 다룹니다.",
    "Multi-component 시나리오에서 MODE A/B/C는 가능한 범위를 계산하지만 BEP는 기존 "
    "MULTI_COMPONENT_BEP_NOT_SUPPORTED 규칙을 그대로 따릅니다 — Scenario Compare가 이를 우회하거나 "
    "단일 component로 축약하지 않습니다.",
    "Scenario Compare는 자동 ranking이나 recommendation을 하지 않습니다 — 여러 시나리오를 나란히 "
    "비교해서 보여주는 descriptive comparison layer일 뿐입니다. '최적 시나리오' 자동 선정은 향후 AI "
    "Pricing Strategy layer의 몫입니다.",
]
for line in sc_guide_lines:
    g.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2)
    c = g.cell(row=r, column=2, value="• " + line)
    c.font = label_font
    c.alignment = Alignment(wrap_text=True, vertical="top")
    g.row_dimensions[r].height = 56
    r += 1
r += 1

g.freeze_panes = "B4"

# ================================================================
# Reference values, computed live from the actual Python engine
# (docs/features/mode_a_current_price/SPEC.md is the formula source of
# truth; core/engine/modes/mode_a.py is the reference implementation).
# Embedding numbers this way — instead of hand-typing them — means the
# workbook can never silently drift from the engine it's supposed to match.
# ================================================================
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.engine.modes.mode_a import run_mode_a  # noqa: E402
from scenario_helpers import make_client_input  # noqa: E402


PARITY_CASES = [
    dict(name="Case 1 — Simple one-time product",
         actual_price=35000, includes_vat=True, vat_rate=0.10, direct_cost=13500,
         channel_fee_rate=0, pg_fee_rate=0.025, delivery=3000, other_var=0),
    dict(name="Case 2 — VAT-inclusive, clean numbers",
         actual_price=11000, includes_vat=True, vat_rate=0.10, direct_cost=4000,
         channel_fee_rate=0, pg_fee_rate=0, delivery=0, other_var=0),
    dict(name="Case 3 — Ecommerce (channel fee + PG fee)",
         actual_price=59000, includes_vat=True, vat_rate=0.10, direct_cost=17000,
         channel_fee_rate=0.13, pg_fee_rate=0.028, delivery=2500, other_var=0),
    dict(name="Case 4 — Incomplete input (UNKNOWN propagation)",
         actual_price=35000, includes_vat=None, vat_rate=None, direct_cost=None,
         channel_fee_rate=None, pg_fee_rate=None, delivery=None, other_var=None),
    # Cases 5-6 specifically regression-test the corrected gross-payment VAT rule (see
    # core/schemas/dependency_rules.md §2 and docs/features/mode_a_current_price/SPEC.md
    # "Rate-based cost items" — an earlier version of both this workbook and the engine
    # wrongly treated price_includes_vat=false as making VAT rate irrelevant even when a
    # rate_of_gross_payment fee (PG fee) was present).
    dict(name="Case 5 — VAT-exclusive display + known VAT rate + gross-payment fee",
         actual_price=8800, includes_vat=False, vat_rate=0.10, direct_cost=3000,
         channel_fee_rate=0, pg_fee_rate=0.04, delivery=200, other_var=0),
    dict(name="Case 6 — VAT-exclusive display + VAT rate UNKNOWN + gross-payment fee",
         actual_price=8800, includes_vat=False, vat_rate=None, direct_cost=3000,
         channel_fee_rate=0, pg_fee_rate=0.04, delivery=200, other_var=0),
]

from scenario_helpers import METRIC_KEYS, METRIC_LABELS  # noqa: E402

for case in PARITY_CASES:
    ci = make_client_input(**{k: v for k, v in case.items() if k != "name"})
    result = run_mode_a(ci)
    m = result["per_component"]["main"]
    case["python_result"] = {k: (m[k]["value"] if m[k]["status"] == "OK" else "UNKNOWN") for k in METRIC_KEYS}

print("Computed Python reference values for", len(PARITY_CASES), "parity cases.")

# ================================================================
# SHEET: 01_SIMULATOR
# ================================================================
s = wb.create_sheet("01_SIMULATOR")
s.sheet_view.showGridLines = False
s.column_dimensions["A"].width = 2
s.column_dimensions["B"].width = 30
s.column_dimensions["C"].width = 16
s.column_dimensions["D"].width = 42
s.column_dimensions["J"].width = 5
s.column_dimensions["J"].hidden = True  # helper column for TEXTJOIN

r = 2
title_row(s, r, "01. MODE A Simulator — Interactive", span=3); r += 2

section_row(s, r, "INPUT (노란 셀만 입력)", span=2); r += 1
ROW_PRODUCT_NAME = r
label(s, r, 2, "Product Name")
input_cell(s, r, 3, "프리미엄 텀블러")
label(s, r, 4, "예시 시나리오 — 자유롭게 바꿔서 실험 가능", italic=True); r += 1

ROW_ACTUAL_PRICE = r
label(s, r, 2, "Actual Price")
input_cell(s, r, 3, 35000, fmt='#,##0')
label(s, r, 4, "실제 판매가격"); r += 1

ROW_INCLUDES_VAT = r
label(s, r, 2, "Price Includes VAT")
input_cell(s, r, 3, True)
label(s, r, 4, "TRUE = 판매가에 VAT 포함 / FALSE = 별도 / 빈칸 = 모름"); r += 1

ROW_VAT_RATE = r
label(s, r, 2, "VAT Rate")
input_cell(s, r, 3, 0.10, fmt="0.0%")
label(s, r, 4, "Price Includes VAT=FALSE면 비워둬도 계산 가능"); r += 1

ROW_DIRECT_COST = r
label(s, r, 2, "Product/Service Direct Cost")
input_cell(s, r, 3, 13500, fmt='#,##0')
label(s, r, 4, "Gross Profit 계산에 반영 (product_service_direct_cost)"); r += 1

ROW_CHANNEL_FEE = r
label(s, r, 2, "Channel Fee Rate")
input_cell(s, r, 3, 0, fmt="0.0%")
label(s, r, 4, "rate_of_net_sales — Net Sales(ex VAT)에 곱함. 채널 없으면 0"); r += 1

ROW_PG_FEE = r
label(s, r, 2, "PG Fee Rate")
input_cell(s, r, 3, 0.025, fmt="0.0%")
label(s, r, 4, "rate_of_gross_payment — Actual Price(결제금액)에 곱함"); r += 1

ROW_DELIVERY = r
label(s, r, 2, "Delivery / Installation Cost")
input_cell(s, r, 3, 3000, fmt='#,##0')
label(s, r, 4, "variable_selling_delivery (Harness 기본 분류)"); r += 1

ROW_OTHER_VAR = r
label(s, r, 2, "Other Variable Selling Cost")
input_cell(s, r, 3, 0, fmt='#,##0')
label(s, r, 4, "기타 판매 변동비"); r += 2

# ---- RESULT ----
section_row(s, r, "RESULT (계산값 — 직접 입력 금지)", span=2); r += 1

C = {
    "actual_price": f"$C${ROW_ACTUAL_PRICE}",
    "includes_vat": f"$C${ROW_INCLUDES_VAT}",
    "vat_rate": f"$C${ROW_VAT_RATE}",
    "direct_cost": f"$C${ROW_DIRECT_COST}",
    "channel_fee": f"$C${ROW_CHANNEL_FEE}",
    "pg_fee": f"$C${ROW_PG_FEE}",
    "delivery": f"$C${ROW_DELIVERY}",
    "other_var": f"$C${ROW_OTHER_VAR}",
}

ROW_EX_VAT = r
ex_vat_formula = (
    f'=IFERROR(IF(ISBLANK({C["actual_price"]}),"미입력",'
    f'IF(ISBLANK({C["includes_vat"]}),"미입력",'
    f'IF({C["includes_vat"]}=FALSE,{C["actual_price"]},'
    f'IF(ISBLANK({C["vat_rate"]}),"미입력",{C["actual_price"]}/(1+{C["vat_rate"]}))))),"계산불가")'
)
label(s, r, 2, "Actual Price ex VAT")
formula_cell(s, r, 3, ex_vat_formula, fmt='#,##0.00')
label(s, r, 4, "= actual_price / (1+vat_rate), 조건부 (SPEC.md §VAT 규칙)")
EX_VAT = f"$C${ROW_EX_VAT}"

# Hidden mirror of ex_vat_formula: gross payment (basis for rate_of_gross_payment fees).
# NOT simply "= actual_price" — that was a real bug this workbook once had (see
# docs/features/mode_a_current_price/SPEC.md "Rate-based cost items" / core/schemas/
# dependency_rules.md §2). Gross payment = net sales grossed back UP by VAT, so the
# "needs vat_rate" branch here is the OPPOSITE one from ex_vat_formula's.
gross_payment_formula = (
    f'=IFERROR(IF(ISBLANK({C["actual_price"]}),"미입력",'
    f'IF(ISBLANK({C["includes_vat"]}),"미입력",'
    f'IF({C["includes_vat"]}=TRUE,{C["actual_price"]},'
    f'IF(ISBLANK({C["vat_rate"]}),"미입력",{C["actual_price"]}*(1+{C["vat_rate"]}))))),"계산불가")'
)
s.cell(row=ROW_EX_VAT, column=10, value=gross_payment_formula)  # hidden helper, column J
GROSS_PAYMENT = f"$J${ROW_EX_VAT}"
r += 1

ROW_DIRECT_TOTAL = r
label(s, r, 2, "Direct Cost Total")
formula_cell(s, r, 3, f'=IFERROR(IF(ISBLANK({C["direct_cost"]}),"미입력",{C["direct_cost"]}),"계산불가")', fmt='#,##0.00')
label(s, r, 4, "product_service_direct_cost 합계"); r += 1
DIRECT_TOTAL = f"$C${ROW_DIRECT_TOTAL}"

ROW_GROSS_PROFIT = r
label(s, r, 2, "Gross Profit")
formula_cell(s, r, 3,
    f'=IFERROR(IF(AND(ISNUMBER({EX_VAT}),ISNUMBER({DIRECT_TOTAL})),{EX_VAT}-{DIRECT_TOTAL},"미입력"),"계산불가")',
    fmt='#,##0.00')
label(s, r, 4, "= Actual Price ex VAT − Direct Cost Total"); r += 1
GROSS_PROFIT = f"$C${ROW_GROSS_PROFIT}"

ROW_GP_RATE = r
label(s, r, 2, "Gross Profit Rate")
# ERROR (계산불가) must be distinguished from UNKNOWN (미입력): when both inputs are known
# numbers but Actual Price ex VAT == 0, this is a genuine division-by-zero CALCULATION_ERROR
# in Python (mode_a.py), not a missing-data UNKNOWN -- an AND-guard that lumps "EX_VAT=0" in
# with "not yet a number" would show "미입력" for both, hiding the ERROR tier from this cell.
formula_cell(s, r, 3,
    f'=IFERROR(IF(OR(NOT(ISNUMBER({GROSS_PROFIT})),NOT(ISNUMBER({EX_VAT}))),"미입력",'
    f'IF({EX_VAT}=0,"계산불가",{GROSS_PROFIT}/{EX_VAT})),"계산불가")',
    fmt="0.00%")
label(s, r, 4, "= Gross Profit / Actual Price ex VAT"); r += 1
GP_RATE = f"$C${ROW_GP_RATE}"

ROW_VAR_TOTAL = r
var_formula = (
    f'=IFERROR(IF(OR(ISBLANK({C["channel_fee"]}),ISBLANK({C["pg_fee"]}),ISBLANK({C["delivery"]}),'
    f'ISBLANK({C["other_var"]}),NOT(ISNUMBER({EX_VAT})),NOT(ISNUMBER({GROSS_PAYMENT}))),"미입력",'
    f'{EX_VAT}*{C["channel_fee"]}+{GROSS_PAYMENT}*{C["pg_fee"]}+{C["delivery"]}+{C["other_var"]}),"계산불가")'
)
label(s, r, 2, "Variable Cost Total")
formula_cell(s, r, 3, var_formula, fmt='#,##0.00')
label(s, r, 4, "channel_fee×NetSales + pg_fee×GrossPayment(=NetSales×(1+VAT)) + delivery + other"); r += 1
VAR_TOTAL = f"$C${ROW_VAR_TOTAL}"

ROW_CM = r
label(s, r, 2, "Contribution Margin")
formula_cell(s, r, 3,
    f'=IFERROR(IF(AND(ISNUMBER({GROSS_PROFIT}),ISNUMBER({VAR_TOTAL})),{GROSS_PROFIT}-{VAR_TOTAL},"미입력"),"계산불가")',
    fmt='#,##0.00')
label(s, r, 4, "= Gross Profit − Variable Cost Total (fixed cost 제외)"); r += 1
CM = f"$C${ROW_CM}"

ROW_CM_RATE = r
label(s, r, 2, "Contribution Margin Rate")
# Same ERROR-vs-UNKNOWN distinction as Gross Profit Rate above.
formula_cell(s, r, 3,
    f'=IFERROR(IF(OR(NOT(ISNUMBER({CM})),NOT(ISNUMBER({EX_VAT}))),"미입력",'
    f'IF({EX_VAT}=0,"계산불가",{CM}/{EX_VAT})),"계산불가")',
    fmt="0.00%")
label(s, r, 4, "= Contribution Margin / Actual Price ex VAT"); r += 2
CM_RATE = f"$C${ROW_CM_RATE}"

# ---- STATUS ----
section_row(s, r, "STATUS", span=2); r += 1

ROW_STATUS_COMPLETE = r
# 3-tier, matching the canonical module-status rule (dependency_rules.md section 5): ERROR
# outranks Incomplete. "계산불가" is this sheet's existing ERROR-equivalent text (from the
# IFERROR(...,"계산불가") wrapper each result formula already has); "미입력" is UNKNOWN. Neither
# underlying result formula is changed here — only how this status cell reads their existing text.
status_result_cells = [EX_VAT, GROSS_PROFIT, GP_RATE, VAR_TOTAL, CM, CM_RATE]
_error_check = "+".join(f'IF({c}="계산불가",1,0)' for c in status_result_cells)
_incomplete_check = "+".join(f'IF(NOT(ISNUMBER({c})),1,0)' for c in status_result_cells)
label(s, r, 2, "Data Complete / Incomplete / Error")
formula_cell(s, r, 3,
    f'=IF(({_error_check})>0,"Error",IF(({_incomplete_check})>0,"Incomplete","Complete"))',
    fmt="General")
r += 1

ROW_STATUS_MISSING = r
# Built without TEXTJOIN (not reliably available across Excel/LibreOffice versions —
# an earlier build produced #NAME? in LibreOffice). Each fragment self-terminates with
# "|"; the display formula strips the trailing "|" and swaps remaining "|" for ", ".
missing_formula = (
    f'=IF(ISBLANK({C["actual_price"]}),"판매가격|","")&'
    f'IF(ISBLANK({C["includes_vat"]}),"VAT포함여부|","")&'
    # VAT rate is a *per-metric* dependency, not "only matters when price includes VAT":
    # needed when includes_vat=TRUE (for Net Sales), OR when includes_vat=FALSE and a
    # PG fee rate is actually configured (for Gross Payment, which PG fee is based on).
    f'IF(AND(NOT(ISBLANK({C["includes_vat"]})),ISBLANK({C["vat_rate"]}),'
    f'OR({C["includes_vat"]}=TRUE,AND({C["includes_vat"]}=FALSE,NOT(ISBLANK({C["pg_fee"]}))))),'
    f'"VAT율|","")&'
    f'IF(ISBLANK({C["direct_cost"]}),"직접원가|","")&'
    f'IF(ISBLANK({C["channel_fee"]}),"채널수수료율|","")&'
    f'IF(ISBLANK({C["pg_fee"]}),"PG수수료율|","")&'
    f'IF(ISBLANK({C["delivery"]}),"배송/설치비|","")&'
    f'IF(ISBLANK({C["other_var"]}),"기타변동비|","")'
)
s.cell(row=r, column=10, value=missing_formula)  # hidden helper, column J
label(s, r, 2, "Missing Inputs")
formula_cell(
    s, r, 3,
    f'=IF($J${r}="","없음",SUBSTITUTE(LEFT($J${r},LEN($J${r})-1),"|",", "))',
    fmt="General", bold=False,
)
r += 1

ROW_STATUS_WARNING = r
label(s, r, 2, "Blocking Warning")
formula_cell(s, r, 3,
    f'=IF(AND(ISNUMBER({GROSS_PROFIT}),ISNUMBER({CM})),"없음 — 핵심 지표 계산 완료",'
    f'"Gross Profit: "&IF(ISNUMBER({GROSS_PROFIT}),"OK","UNKNOWN")&" | Contribution Margin: "&IF(ISNUMBER({CM}),"OK","UNKNOWN"))',
    fmt="General", bold=False)
r += 2

# ---- DASHBOARD CARD ----
section_row(s, r, "DASHBOARD CARD", span=5); r += 1
card_top = r
cards = [
    ("Current Price", C["actual_price"], '#,##0'),
    ("Net Sales", EX_VAT, '#,##0'),
    ("Gross Profit", GROSS_PROFIT, '#,##0'),
    ("GP Rate", GP_RATE, "0.0%"),
    ("Contribution Margin", CM, '#,##0'),
    ("CM Rate", CM_RATE, "0.0%"),
]
card_w, gap = 2, 1
col = 2
for i, (label_txt, ref, fmt) in enumerate(cards):
    if i == 3:  # wrap to second row after 3 cards
        col = 2
        card_top = r + 3
    cr = card_top
    s.merge_cells(start_row=cr, start_column=col, end_row=cr, end_column=col + card_w - 1)
    lc = s.cell(row=cr, column=col, value=label_txt)
    lc.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    lc.fill = PatternFill("solid", fgColor=NAVY)
    lc.alignment = Alignment(horizontal="center", vertical="center")
    s.merge_cells(start_row=cr + 1, start_column=col, end_row=cr + 1, end_column=col + card_w - 1)
    vc = s.cell(row=cr + 1, column=col, value=f"={ref}")
    vc.font = Font(name="Calibri", size=16, bold=True, color=INK)
    vc.number_format = fmt
    vc.fill = PatternFill("solid", fgColor=LIGHT)
    vc.alignment = Alignment(horizontal="center", vertical="center")
    vc.border = box
    s.row_dimensions[cr + 1].height = 26
    # conditional formatting: not-a-number -> red/orange tint
    vcoord = vc.coordinate
    s.conditional_formatting.add(
        vcoord,
        FormulaRule(formula=[f"NOT(ISNUMBER({vcoord}))"], fill=PatternFill("solid", fgColor=RED_BG)),
    )
    s.conditional_formatting.add(
        vcoord,
        FormulaRule(formula=[f"ISNUMBER({vcoord})"], fill=PatternFill("solid", fgColor=GREEN_BG)),
    )
    col += card_w + gap

s.freeze_panes = "B4"

# add data validation for the boolean input cell
dv = DataValidation(type="list", formula1='"TRUE,FALSE"', allow_blank=True)
s.add_data_validation(dv)
dv.add(s.cell(row=ROW_INCLUDES_VAT, column=3))

print("01_SIMULATOR_OK")

# ================================================================
# SHEET: 02_CALCULATION
# ================================================================
cflow = wb.create_sheet("02_CALCULATION")
cflow.sheet_view.showGridLines = False
cflow.column_dimensions["A"].width = 2
cflow.column_dimensions["B"].width = 26
cflow.column_dimensions["C"].width = 46
cflow.column_dimensions["D"].width = 20

r = 2
title_row(cflow, r, "02. Calculation Flow — 교육/QA용 (01_SIMULATOR 값을 그대로 참조)", span=2); r += 2

flow_steps = [
    ("① Actual Price", f"='01_SIMULATOR'!{C['actual_price']}", "입력된 판매가격 그대로"),
    ("② VAT 처리", "", "price_includes_vat=FALSE → 그대로 사용 / TRUE → ÷(1+vat_rate)"),
    ("③ Net Sales (ex VAT)", f"='01_SIMULATOR'!{EX_VAT}", "①을 VAT 규칙대로 변환한 값"),
    ("④ Direct Cost", f"='01_SIMULATOR'!{C['direct_cost']}", "product_service_direct_cost"),
    ("⑤ Gross Profit", f"='01_SIMULATOR'!{GROSS_PROFIT}", "③ − ④"),
    ("⑥ Variable Selling Cost", f"='01_SIMULATOR'!{VAR_TOTAL}", "channel/PG/배송/기타 변동비 합"),
    ("⑦ Contribution Margin", f"='01_SIMULATOR'!{CM}", "⑤ − ⑥ (고정비 제외)"),
]
hdr_row = r
for i, h in enumerate(["Step", "Live Value (from 01_SIMULATOR)", "Formula / Rule"]):
    cc = cflow.cell(row=r, column=2 + i, value=h)
    cc.font = header_font
    cc.fill = header_fill
    cc.alignment = Alignment(horizontal="center")
r += 1
for i, (step, formula, rule) in enumerate(flow_steps):
    cflow.cell(row=r, column=2, value=step).font = value_font
    cflow.cell(row=r, column=2).border = box
    if formula:
        vc = cflow.cell(row=r, column=3, value=formula)
        vc.number_format = '#,##0.00'
    else:
        vc = cflow.cell(row=r, column=3, value="(VAT 포함여부에 따라 분기 — 결과는 다음 행 ③에 반영됨)")
        vc.font = note_font
    vc.border = box
    vc.alignment = Alignment(horizontal="right" if formula else "left")
    rc = cflow.cell(row=r, column=4, value=rule)
    rc.font = label_font
    rc.border = box
    rc.alignment = Alignment(wrap_text=True, vertical="center")
    cflow.row_dimensions[r].height = 30
    r += 1
    if i < len(flow_steps) - 1:
        ac = cflow.cell(row=r, column=2, value="↓")
        ac.font = Font(size=14, bold=True, color=TEAL)
        ac.alignment = Alignment(horizontal="center")
        r += 1

cflow.freeze_panes = "B4"
print("02_CALCULATION_OK")

# ================================================================
# SHEET: 03_PARITY_TEST
# ================================================================
p = wb.create_sheet("03_PARITY_TEST")
p.sheet_view.showGridLines = False
p.column_dimensions["A"].width = 2
p.column_dimensions["B"].width = 26
for col in "CDEFG":
    p.column_dimensions[col].width = 15
p.column_dimensions["H"].width = 10

r = 2
title_row(p, r, "03. Python Engine vs Excel Formula — Parity Test", span=6); r += 1
p.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
c = p.cell(row=r, column=2, value=(
    "각 케이스는 Excel에 동일 입력값을 리터럴로 심어 01_SIMULATOR와 같은 수식 패턴으로 독립 재계산하고, "
    "Python 참조값(core/engine/modes/mode_a.py 실행 결과, 빌드 시점에 고정)과 비교합니다. 허용오차 0.01(금액) / 0.0001(비율)."
))
c.font = note_font
c.alignment = Alignment(wrap_text=True, vertical="top")
p.row_dimensions[r].height = 30
r += 2

TOL_AMOUNT = 0.01
TOL_RATE = 0.0001
RATE_METRICS = {"gross_profit_rate", "contribution_margin_rate"}

overall_pass_cells = []

for case in PARITY_CASES:
    section_row(p, r, case["name"], span=5); r += 1
    hdr_row = r
    for i, h in enumerate(["Metric", "Excel Result", "Python Reference", "Difference", "PASS / FAIL"]):
        cc = p.cell(row=r, column=2 + i, value=h)
        cc.font = header_font
        cc.fill = header_fill
        cc.alignment = Alignment(horizontal="center")
    r += 1

    # --- local literal inputs for this case (hidden-ish, small, columns further right) ---
    li = {}
    input_col = 9  # column I onward, local scratch inputs for this block
    p.cell(row=r, column=input_col - 1, value="(local inputs)").font = note_font
    local_row = r
    field_order = ["actual_price", "includes_vat", "vat_rate", "direct_cost",
                   "channel_fee_rate", "pg_fee_rate", "delivery", "other_var"]
    for j, field in enumerate(field_order):
        cell = p.cell(row=local_row, column=input_col + j, value=case[field])
        li[field] = f"${get_column_letter(input_col + j)}${local_row}"
    for col_idx in range(input_col, input_col + len(field_order)):
        p.column_dimensions[get_column_letter(col_idx)].hidden = True

    ex_vat_f = (
        f'=IFERROR(IF(ISBLANK({li["actual_price"]}),"미입력",'
        f'IF(ISBLANK({li["includes_vat"]}),"미입력",'
        f'IF({li["includes_vat"]}=FALSE,{li["actual_price"]},'
        f'IF(ISBLANK({li["vat_rate"]}),"미입력",{li["actual_price"]}/(1+{li["vat_rate"]}))))),"계산불가")'
    )
    direct_f = f'=IFERROR(IF(ISBLANK({li["direct_cost"]}),"미입력",{li["direct_cost"]}),"계산불가")'

    local_row2 = local_row + 1
    ex_vat_cell = p.cell(row=local_row2, column=input_col, value=ex_vat_f).coordinate
    direct_cell = p.cell(row=local_row2, column=input_col + 1, value=direct_f).coordinate
    gp_f = f'=IFERROR(IF(AND(ISNUMBER({ex_vat_cell}),ISNUMBER({direct_cell})),{ex_vat_cell}-{direct_cell},"미입력"),"계산불가")'
    gp_cell = p.cell(row=local_row2, column=input_col + 2, value=gp_f).coordinate
    gpr_f = (
        f'=IFERROR(IF(OR(NOT(ISNUMBER({gp_cell})),NOT(ISNUMBER({ex_vat_cell}))),"미입력",'
        f'IF({ex_vat_cell}=0,"계산불가",{gp_cell}/{ex_vat_cell})),"계산불가")'
    )
    gpr_cell = p.cell(row=local_row2, column=input_col + 3, value=gpr_f).coordinate
    # Gross payment mirror (see build note on gross_payment_formula above — same corrected logic).
    gross_payment_f = (
        f'=IFERROR(IF(ISBLANK({li["actual_price"]}),"미입력",'
        f'IF(ISBLANK({li["includes_vat"]}),"미입력",'
        f'IF({li["includes_vat"]}=TRUE,{li["actual_price"]},'
        f'IF(ISBLANK({li["vat_rate"]}),"미입력",{li["actual_price"]}*(1+{li["vat_rate"]}))))),"계산불가")'
    )
    gross_payment_cell = p.cell(row=local_row2, column=input_col + 7, value=gross_payment_f).coordinate
    var_f = (
        f'=IFERROR(IF(OR(ISBLANK({li["channel_fee_rate"]}),ISBLANK({li["pg_fee_rate"]}),ISBLANK({li["delivery"]}),'
        f'ISBLANK({li["other_var"]}),NOT(ISNUMBER({ex_vat_cell})),NOT(ISNUMBER({gross_payment_cell}))),"미입력",'
        f'{ex_vat_cell}*{li["channel_fee_rate"]}+{gross_payment_cell}*{li["pg_fee_rate"]}+{li["delivery"]}+{li["other_var"]}),"계산불가")'
    )
    var_cell = p.cell(row=local_row2, column=input_col + 4, value=var_f).coordinate
    cm_f = f'=IFERROR(IF(AND(ISNUMBER({gp_cell}),ISNUMBER({var_cell})),{gp_cell}-{var_cell},"미입력"),"계산불가")'
    cm_cell = p.cell(row=local_row2, column=input_col + 5, value=cm_f).coordinate
    cmr_f = (
        f'=IFERROR(IF(OR(NOT(ISNUMBER({cm_cell})),NOT(ISNUMBER({ex_vat_cell}))),"미입력",'
        f'IF({ex_vat_cell}=0,"계산불가",{cm_cell}/{ex_vat_cell})),"계산불가")'
    )
    cmr_cell = p.cell(row=local_row2, column=input_col + 6, value=cmr_f).coordinate
    for col_idx in range(input_col, input_col + 8):
        p.column_dimensions[get_column_letter(col_idx)].hidden = True

    excel_cell_for = {
        "actual_price_ex_vat": ex_vat_cell, "direct_cost_total": direct_cell,
        "gross_profit": gp_cell, "gross_profit_rate": gpr_cell,
        "variable_cost_total": var_cell, "contribution_margin": cm_cell,
        "contribution_margin_rate": cmr_cell,
    }

    for mk in METRIC_KEYS:
        label(p, r, 2, METRIC_LABELS[mk])
        excel_ref = excel_cell_for[mk]
        fmt = "0.00%" if mk in RATE_METRICS else '#,##0.00'
        ec = formula_cell(p, r, 3, f"={excel_ref}", fmt=fmt, bold=False)

        py_val = case["python_result"][mk]
        pc = p.cell(row=r, column=4, value=py_val if py_val != "UNKNOWN" else "UNKNOWN")
        pc.border = box
        pc.alignment = Alignment(horizontal="right")
        if py_val != "UNKNOWN":
            pc.number_format = fmt

        tol = TOL_RATE if mk in RATE_METRICS else TOL_AMOUNT
        py_cell = pc.coordinate
        diff_f = f'=IF(ISNUMBER({py_cell}),IF(ISNUMBER({excel_ref}),ABS({excel_ref}-{py_cell}),"N/A"),"N/A")'
        dc = formula_cell(p, r, 5, diff_f, fmt='0.0000', bold=False)

        pass_f = (
            f'=IF(ISNUMBER({py_cell}),'
            f'IF(AND(ISNUMBER({excel_ref}),ABS({excel_ref}-{py_cell})<={tol}),"PASS","FAIL"),'
            f'IF(NOT(ISNUMBER({excel_ref})),"PASS","FAIL"))'
        )
        pcell = formula_cell(p, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells.append(pcell.coordinate)
        p.conditional_formatting.add(
            pcell.coordinate,
            FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)),
        )
        p.conditional_formatting.add(
            pcell.coordinate,
            FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)),
        )
        r += 1
    r += 1

section_row(p, r, "Overall", span=2); r += 1
label(p, r, 2, "All metrics PASS?")
overall_range = ",".join(overall_pass_cells)
overall_f = f'=IF(COUNTIF({overall_pass_cells[0]}:{overall_pass_cells[-1]},"FAIL")=0,"ALL PASS","SOME FAILED")'
# COUNTIF needs a contiguous range; cells are contiguous within/among blocks by construction (col G throughout)
oc = formula_cell(p, r, 3, overall_f, fmt="General", bold=True)
p.conditional_formatting.add(oc.coordinate, FormulaRule(formula=[f'{oc.coordinate}="SOME FAILED"'], fill=PatternFill("solid", fgColor=RED_BG)))
p.conditional_formatting.add(oc.coordinate, FormulaRule(formula=[f'{oc.coordinate}="ALL PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))

p.freeze_panes = "B4"
print("03_PARITY_TEST_OK")

# ================================================================
# SHEET: 04_MODE_B_SIMULATOR
# ================================================================
from core.engine.modes.mode_b import run_mode_b  # noqa: E402
from scenario_helpers import make_client_input_b, METRIC_KEYS_B, METRIC_LABELS_B  # noqa: E402

sb = wb.create_sheet("04_MODE_B_SIMULATOR")
sb.sheet_view.showGridLines = False
sb.column_dimensions["A"].width = 2
sb.column_dimensions["B"].width = 32
sb.column_dimensions["C"].width = 16
sb.column_dimensions["D"].width = 48

r = 2
title_row(sb, r, "04. MODE B Simulator — Target Price (Interactive)", span=3); r += 2

section_row(sb, r, "INPUT (노란 셀만 입력, 단일 컴포넌트 / shared cost 없음 기준)", span=2); r += 1

ROW_TARGET_CM = r
label(sb, r, 2, "Target Contribution Margin Rate (t)")
input_cell(sb, r, 3, 0.30, fmt="0.0%")
label(sb, r, 4, "0 이상 1 미만이어야 함 (>=1 또는 <0은 ERROR)"); r += 1

ROW_DIRECT_COST_B = r
label(sb, r, 2, "Fixed-Amount Direct + Variable Cost (C)")
input_cell(sb, r, 3, 10000, fmt='#,##0')
label(sb, r, 4, "직접원가 + 금액형 변동비 합계 (rate 기반 항목 제외)"); r += 1

ROW_NET_SALES_FEE = r
label(sb, r, 2, "Net-Sales Fee Rate (b)")
input_cell(sb, r, 3, 0, fmt="0.0%")
label(sb, r, 4, "rate_of_net_sales 합계 — Net Sales(N)에 곱함. 없으면 0"); r += 1

ROW_GROSS_PAYMENT_FEE = r
label(sb, r, 2, "Gross-Payment Fee Rate (a)")
input_cell(sb, r, 3, 0.05, fmt="0.0%")
label(sb, r, 4, "rate_of_gross_payment 합계 — Gross Payment(G)에 곱함. 없으면 0"); r += 1

ROW_INCLUDES_VAT_B = r
label(sb, r, 2, "Price Includes VAT")
input_cell(sb, r, 3, False)
label(sb, r, 4, "TRUE→표시가=G / FALSE→표시가=N / 빈칸=모름(UNKNOWN)"); r += 1

ROW_VAT_RATE_B = r
label(sb, r, 2, "VAT Rate (v)")
input_cell(sb, r, 3, 0.10, fmt="0.0%")
label(sb, r, 4, "a=0이면 N 계산에 불필요. G는 a와 무관하게 항상 필요 (SPEC.md §3)"); r += 1

ROW_DISCOUNT_RATE = r
label(sb, r, 2, "Discount Rate")
input_cell(sb, r, 3, None, fmt="0.0%")
label(sb, r, 4, "0 이상 1 미만이어야 함. 빈칸=UNKNOWN → 정가 계산 불가"); r += 1

ROW_SHARED_FLAG = r
label(sb, r, 2, "Shared Cost Status (Excel simulation control — not a schema field)")
input_cell(sb, r, 3, "none")
label(sb, r, 4, (
    "Excel-only simulation control. NOT a field in client_input.schema.json — the production "
    "Python engine (core/engine/modes/mode_b.py) derives this state from actual cost item / "
    "applies_to_component / allocation_rule data, never from a flag like this. "
    "none=shared 비용 없음(정상 계산) / unresolved=by_component_revenue·fixed_share 등 배부 "
    "미구현(모든 결과 UNKNOWN) / invalid=shared+direct 모순 설정(모든 결과 ERROR). "
    "실제 배부 엔진은 구현하지 않음 — 미지원 상태를 조용히 숫자로 만들지 않는지만 검증"
), wrap=True); r += 2

REFS_B = {
    "t": f"$C${ROW_TARGET_CM}", "c": f"$C${ROW_DIRECT_COST_B}", "b": f"$C${ROW_NET_SALES_FEE}",
    "a": f"$C${ROW_GROSS_PAYMENT_FEE}", "v": f"$C${ROW_VAT_RATE_B}",
    "incvat": f"$C${ROW_INCLUDES_VAT_B}", "disc": f"$C${ROW_DISCOUNT_RATE}",
    "shared_flag": f"$C${ROW_SHARED_FLAG}",
}

section_row(sb, r, "RESULT (계산값 — 직접 입력 금지)", span=2); r += 1

RESULT_ROWS_B = {}
for key in METRIC_KEYS_B:
    RESULT_ROWS_B[key] = r
    r += 1

result_cell_map = {key: (RESULT_ROWS_B[key], 3) for key in METRIC_KEYS_B}
RESULT_CELLS_B = build_mode_b_formulas(sb, result_cell_map, REFS_B)

result_notes = {
    "denominator": "D = 1 - t - b - a(1+v). D<=0 → ERROR (목표 불가능)",
    "required_net_sales_ex_vat": "N = C / D",
    "required_gross_payment_incl_vat": "G = N × (1+v) — 항상 v 필요",
    "required_selling_price": "price_includes_vat=FALSE→N / TRUE→G / 빈칸→UNKNOWN",
    "required_list_price": "= 판매가 / (1 - discount_rate)",
    "expected_contribution_margin": "= N - C - b×N - a×G (역산식과 독립적인 비용구조 재계산)",
    "expected_contribution_margin_rate": "= CM / N — 아래 Self-Check에서 목표 t와 별도 대조",
}
for key in METRIC_KEYS_B:
    row = RESULT_ROWS_B[key]
    label(sb, row, 2, METRIC_LABELS_B[key])
    fmt = "0.00%" if key == "expected_contribution_margin_rate" else ('#,##0.00' if key != "denominator" else "0.0000")
    c = sb.cell(row=row, column=3)
    c.font = value_font
    c.border = box
    c.alignment = Alignment(vertical="center", horizontal="right")
    c.number_format = fmt
    label(sb, row, 4, result_notes[key])
    coord = c.coordinate
    sb.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="ERROR"'], fill=PatternFill("solid", fgColor=RED_BG)))
    sb.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="UNKNOWN"'], fill=PatternFill("solid", fgColor=YELLOW)))
    sb.conditional_formatting.add(coord, FormulaRule(formula=[f'ISNUMBER({coord})'], fill=PatternFill("solid", fgColor=GREEN_BG)))
r += 1

ROW_SELF_CHECK = r
label(sb, r, 2, "Self-Check: |CMR − t| ≤ 0.0001?")
selfcheck_cell_b = build_self_check_cell(sb, r, 3, RESULT_CELLS_B["expected_contribution_margin_rate"], REFS_B["t"])
sc_cell_obj = sb.cell(row=r, column=3)
sc_cell_obj.font = value_font
sc_cell_obj.border = box
sc_cell_obj.alignment = Alignment(vertical="center", horizontal="right")
label(sb, r, 4, (
    "역산식(N=C/D)과 독립적으로 재계산한 CMR(=CM/N)이 목표 t와 tolerance 내에서 일치하는지 진단. "
    "MODE B의 공식 출력 metric은 아님 — 산술 오류를 잡기 위한 진단용."
), wrap=True)
sb.conditional_formatting.add(selfcheck_cell_b, FormulaRule(formula=[f'{selfcheck_cell_b}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
sb.conditional_formatting.add(selfcheck_cell_b, FormulaRule(formula=[f'{selfcheck_cell_b}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
r += 1

section_row(sb, r, "STATUS", span=2); r += 1
ROW_STATUS_B = r
status_metric_cells = [RESULT_CELLS_B[k] for k in METRIC_KEYS_B]
error_check = "+".join(f'IF({cell}="ERROR",1,0)' for cell in status_metric_cells)
unknown_check = "+".join(f'IF({cell}="UNKNOWN",1,0)' for cell in status_metric_cells)
status_formula = (
    f'=IF(({error_check})>0,"ERROR — 목표 불가능 또는 입력값 모순",'
    f'IF(({unknown_check})>0,"INCOMPLETE — 일부 지표 UNKNOWN","OK — 전체 계산 완료"))'
)
label(sb, r, 2, "Overall Status")
sc = formula_cell(sb, r, 3, status_formula, fmt="General")
sb.column_dimensions["C"].width = 16
sb.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
sc.alignment = Alignment(horizontal="left")
r += 1

label(sb, r, 2, "blank = UNKNOWN / 0 = explicit zero", italic=True)
r += 2

# ---- DASHBOARD CARD ----
section_row(sb, r, "DASHBOARD CARD", span=5); r += 1
card_top = r
cards_b = [
    ("Required Net Sales ex VAT", RESULT_CELLS_B["required_net_sales_ex_vat"], '#,##0'),
    ("Required Gross Payment", RESULT_CELLS_B["required_gross_payment_incl_vat"], '#,##0'),
    ("Required Selling Price", RESULT_CELLS_B["required_selling_price"], '#,##0'),
    ("Required List Price", RESULT_CELLS_B["required_list_price"], '#,##0'),
    ("Expected CM", RESULT_CELLS_B["expected_contribution_margin"], '#,##0'),
    ("Expected CM Rate", RESULT_CELLS_B["expected_contribution_margin_rate"], "0.0%"),
]
card_w, gap = 2, 1
col = 2
for i, (label_txt, ref, fmt) in enumerate(cards_b):
    if i == 3:
        col = 2
        card_top = r + 3
    cr = card_top
    sb.merge_cells(start_row=cr, start_column=col, end_row=cr, end_column=col + card_w - 1)
    lc = sb.cell(row=cr, column=col, value=label_txt)
    lc.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    lc.fill = PatternFill("solid", fgColor=NAVY)
    lc.alignment = Alignment(horizontal="center", vertical="center")
    sb.merge_cells(start_row=cr + 1, start_column=col, end_row=cr + 1, end_column=col + card_w - 1)
    vc = sb.cell(row=cr + 1, column=col, value=f"={ref}")
    vc.font = Font(name="Calibri", size=16, bold=True, color=INK)
    vc.number_format = fmt
    vc.fill = PatternFill("solid", fgColor=LIGHT)
    vc.alignment = Alignment(horizontal="center", vertical="center")
    vc.border = box
    sb.row_dimensions[cr + 1].height = 26
    vcoord = vc.coordinate
    sb.conditional_formatting.add(vcoord, FormulaRule(formula=[f"NOT(ISNUMBER({vcoord}))"], fill=PatternFill("solid", fgColor=RED_BG)))
    sb.conditional_formatting.add(vcoord, FormulaRule(formula=[f"ISNUMBER({vcoord})"], fill=PatternFill("solid", fgColor=GREEN_BG)))
    col += card_w + gap

sb.freeze_panes = "B4"
dv_b = DataValidation(type="list", formula1='"TRUE,FALSE"', allow_blank=True)
sb.add_data_validation(dv_b)
dv_b.add(sb.cell(row=ROW_INCLUDES_VAT_B, column=3))

dv_shared = DataValidation(type="list", formula1='"none,unresolved,invalid"', allow_blank=False)
sb.add_data_validation(dv_shared)
dv_shared.add(sb.cell(row=ROW_SHARED_FLAG, column=3))
print("04_MODE_B_SIMULATOR_OK")

# ================================================================
# SHEET: 05_MODE_B_PARITY_TEST
# ================================================================
pb = wb.create_sheet("05_MODE_B_PARITY_TEST")
pb.sheet_view.showGridLines = False
pb.column_dimensions["A"].width = 2
pb.column_dimensions["B"].width = 30
for col in "CDEFG":
    pb.column_dimensions[col].width = 16
pb.column_dimensions["H"].width = 10

r = 2
title_row(pb, r, "05. Python Engine vs Excel Formula — MODE B Parity Test", span=6); r += 1
pb.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
c = pb.cell(row=r, column=2, value=(
    "각 케이스는 Excel에 동일 입력값을 리터럴로 심어 04_MODE_B_SIMULATOR와 같은 수식(build_mode_b_formulas)으로 "
    "독립 재계산하고, Python 참조값(core/engine/modes/mode_b.py 실행 결과, 빌드 시점에 고정)과 비교합니다. "
    "허용오차 0.01(금액) / 0.0001(비율). #14/#15는 shared-cost 시나리오로, 실제 배부(allocation) 금액을 계산하지는 "
    "않지만 Shared Cost Status 플래그를 통해 Excel이 '미지원 상태를 UNKNOWN/ERROR로 정확히 표시하는지'를 실시간으로 "
    "평가합니다 — 다른 13개 케이스와 동일하게 15/15 전부 live parity입니다."
))
c.font = note_font
c.alignment = Alignment(wrap_text=True, vertical="top")
pb.row_dimensions[r].height = 44
r += 2

TOL_AMOUNT_B = 0.01
TOL_RATE_B = 0.0001
RATE_METRICS_B = {"expected_contribution_margin_rate"}
FIELD_ORDER_B = ["target_cm_rate", "direct_cost", "net_sales_fee_rate", "gross_payment_fee_rate",
                  "vat_rate", "includes_vat", "discount_rate", "shared_flag"]

# Numeric fields default to 0 (not None) when a scenario means "explicitly no fee", matching
# SPEC.md's null != 0 principle: only fields intentionally testing UNKNOWN pass None.
# shared_flag defaults to "none" (no shared-cost complication) for every case except #14/#15 —
# see build_mode_b_formulas' docstring for what "unresolved"/"invalid" do to the formula chain.
# extra_cost_items (only set on #14/#15) is Python-side only: it makes the Python reference
# value come from an actual shared-cost Client Input, not from the flag.
PARITY_CASES_B = [
    dict(name="1. Simple — no rate cost at all (TC1)",
         target_cm_rate=0.4, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="2. Net-sales fee only (TC2)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="3. Gross-payment fee only, VAT-exclusive display (TC3)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0.05,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="4. VAT-inclusive display, both fee types (TC4)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03,
         vat_rate=0.10, includes_vat=True, discount_rate=None, shared_flag="none"),
    dict(name="5. VAT-exclusive display, both fee types (TC5)",
         target_cm_rate=0.25, direct_cost=8000, net_sales_fee_rate=0.05, gross_payment_fee_rate=0.02,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="6. VAT-exclusive, VAT UNKNOWN, gross-payment fee (TC11)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0.05,
         vat_rate=None, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="7. VAT-exclusive, VAT UNKNOWN, net-sales fee only (TC12)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0,
         vat_rate=None, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="8. VAT-inclusive display, VAT UNKNOWN",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0,
         vat_rate=None, includes_vat=True, discount_rate=None, shared_flag="none"),
    dict(name="9. Discount rate = 0",
         target_cm_rate=0.4, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         vat_rate=0.10, includes_vat=False, discount_rate=0, shared_flag="none"),
    dict(name="10. Discount rate normal value (TC6, on top of TC4)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0.1, gross_payment_fee_rate=0.03,
         vat_rate=0.10, includes_vat=True, discount_rate=0.10, shared_flag="none"),
    dict(name="11. Denominator <= 0 (TC7)",
         target_cm_rate=0.5, direct_cost=10000, net_sales_fee_rate=0.3, gross_payment_fee_rate=0.3,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="12. Explicit zero rate (TC9)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0.05,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="none"),
    dict(name="13. UNKNOWN cost (TC8)",
         target_cm_rate=0.4, direct_cost=None, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="none"),
    # #14/#15: shared-cost allocation. Excel does NOT compute an allocation amount — the
    # Shared Cost Status flag only short-circuits denominator to UNKNOWN/ERROR, exactly mirroring
    # what core/engine/modes/mode_b.py actually does for these two configurations (test_18-style
    # for #14, test_21b-style for #15 in tests/test_mode_b.py). The other numeric inputs here
    # match the underlying scenario's non-shared inputs so the Python reference is computed from
    # a real Client Input with the shared item, not invented to fit the flag.
    dict(name="14. Shared cost: fixed_share (unresolved allocation)",
         target_cm_rate=0.3, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="unresolved",
         extra_cost_items=[{
             "item_id": "shared_channel_fee", "label": "공유 채널수수료", "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
             "applies_to_component": "shared", "allocation_rule": "fixed_share",
         }]),
    dict(name="15. Shared cost: shared + direct (invalid configuration)",
         target_cm_rate=0.4, direct_cost=10000, net_sales_fee_rate=0, gross_payment_fee_rate=0,
         vat_rate=0.10, includes_vat=False, discount_rate=None, shared_flag="invalid",
         extra_cost_items=[{
             "item_id": "shared_channel_direct", "label": "모순 설정: shared + direct 수수료",
             "cost_category": "variable_selling_delivery",
             "amount": None, "rate": 0.1, "currency": None, "basis": "rate_of_net_sales",
             "applies_to_component": "shared", "allocation_rule": "direct",
         }]),
]

for case in PARITY_CASES_B:
    ci_kwargs = {k: v for k, v in case.items() if k not in ("name", "shared_flag", "extra_cost_items")}
    ci_kwargs["extra_cost_items"] = case.get("extra_cost_items")
    ci = make_client_input_b(**ci_kwargs)
    result = run_mode_b(ci)
    m = result["per_component"]["main"]
    case["python_result"] = {k: (m[k]["value"] if m[k]["status"] == "OK" else m[k]["status"]) for k in METRIC_KEYS_B}

overall_pass_cells_b = []

for case in PARITY_CASES_B:
    section_row(pb, r, case["name"], span=5); r += 1
    for i, h in enumerate(["Metric", "Excel Result", "Python Reference", "Difference", "PASS / FAIL"]):
        cc = pb.cell(row=r, column=2 + i, value=h)
        cc.font = header_font
        cc.fill = header_fill
        cc.alignment = Alignment(horizontal="center")
    r += 1

    input_col = 9
    local_row = r
    li = {}
    for j, field in enumerate(FIELD_ORDER_B):
        val = case[field]
        cell = pb.cell(row=local_row, column=input_col + j, value=val)
        li[field] = f"${get_column_letter(input_col + j)}${local_row}"
    for col_idx in range(input_col, input_col + len(FIELD_ORDER_B) + 8):
        pb.column_dimensions[get_column_letter(col_idx)].hidden = True

    refs_local = {
        "t": li["target_cm_rate"], "c": li["direct_cost"], "b": li["net_sales_fee_rate"],
        "a": li["gross_payment_fee_rate"], "v": li["vat_rate"], "incvat": li["includes_vat"],
        "disc": li["discount_rate"], "shared_flag": li["shared_flag"],
    }
    result_col_start = input_col + len(FIELD_ORDER_B)
    cell_map_local = {key: (local_row, result_col_start + i) for i, key in enumerate(METRIC_KEYS_B)}
    excel_cell_for = build_mode_b_formulas(pb, cell_map_local, refs_local)

    for mk in METRIC_KEYS_B:
        label(pb, r, 2, METRIC_LABELS_B[mk])
        excel_ref = excel_cell_for[mk]
        fmt = "0.00%" if mk in RATE_METRICS_B else ('0.0000' if mk == "denominator" else '#,##0.00')
        formula_cell(pb, r, 3, f"={excel_ref}", fmt=fmt, bold=False)

        py_val = case["python_result"][mk]
        pc = pb.cell(row=r, column=4, value=py_val)
        pc.border = box
        pc.alignment = Alignment(horizontal="right")
        if isinstance(py_val, (int, float)):
            pc.number_format = fmt

        tol = TOL_RATE_B if mk in RATE_METRICS_B else TOL_AMOUNT_B
        py_cell = pc.coordinate
        diff_f = f'=IF(ISNUMBER({py_cell}),IF(ISNUMBER({excel_ref}),ABS({excel_ref}-{py_cell}),"N/A"),"N/A")'
        formula_cell(pb, r, 5, diff_f, fmt='0.0000', bold=False)

        pass_f = (
            f'=IF(ISNUMBER({py_cell}),'
            f'IF(AND(ISNUMBER({excel_ref}),ABS({excel_ref}-{py_cell})<={tol}),"PASS","FAIL"),'
            f'IF(AND(NOT(ISNUMBER({excel_ref})),{excel_ref}={py_cell}),"PASS","FAIL"))'
        )
        pcell = formula_cell(pb, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells_b.append(pcell.coordinate)
        pb.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
        pb.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
        r += 1
    r += 1

section_row(pb, r, "Overall (all 15 scenarios — #14/#15 included, all live Excel evaluation)", span=2); r += 1
label(pb, r, 2, "All metrics PASS?")
overall_f_b = f'=IF(COUNTIF({overall_pass_cells_b[0]}:{overall_pass_cells_b[-1]},"FAIL")=0,"ALL PASS","SOME FAILED")'
oc_b = formula_cell(pb, r, 3, overall_f_b, fmt="General", bold=True)
pb.conditional_formatting.add(oc_b.coordinate, FormulaRule(formula=[f'{oc_b.coordinate}="SOME FAILED"'], fill=PatternFill("solid", fgColor=RED_BG)))
pb.conditional_formatting.add(oc_b.coordinate, FormulaRule(formula=[f'{oc_b.coordinate}="ALL PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))

pb.freeze_panes = "B4"
print("05_MODE_B_PARITY_TEST_OK")

# ================================================================
# SHEET: 06_MODE_C_SIMULATOR
# ================================================================
from core.engine.modes.mode_c import run_mode_c  # noqa: E402
from scenario_helpers import make_client_input_c, METRIC_KEYS_C, METRIC_LABELS_C  # noqa: E402

sc = wb.create_sheet("06_MODE_C_SIMULATOR")
sc.sheet_view.showGridLines = False
sc.column_dimensions["A"].width = 2
sc.column_dimensions["B"].width = 34
sc.column_dimensions["C"].width = 16
sc.column_dimensions["D"].width = 50

r = 2
title_row(sc, r, "06. MODE C Simulator — Allowable Direct Cost (Interactive)", span=3); r += 2

section_row(sc, r, "INPUT (노란 셀만 입력, 단일 컴포넌트 기준)", span=2); r += 1

ROW_TARGET_MARKET_PRICE = r
label(sc, r, 2, "Target Market Price")
input_cell(sc, r, 3, 110000, fmt='#,##0')
label(sc, r, 4, "product.price_components[].target_market_price — effective(할인 반영 후) 거래가격"); r += 1

ROW_INCLUDES_VAT_C = r
label(sc, r, 2, "Price Includes VAT")
input_cell(sc, r, 3, True)
label(sc, r, 4, "TRUE=시장가에 VAT 포함 / FALSE=별도 / 빈칸=모름"); r += 1

ROW_VAT_RATE_C = r
label(sc, r, 2, "VAT Rate (v)")
input_cell(sc, r, 3, 0.10, fmt="0.0%")
label(sc, r, 4, "a=0이면 ADC 계산에 불필요. N/G는 각자의 조건에서만 필요 (SPEC.md §6)"); r += 1

ROW_TARGET_CM_C = r
label(sc, r, 2, "Target Contribution Margin Rate (t)")
input_cell(sc, r, 3, 0.30, fmt="0.0%")
label(sc, r, 4, "0 이상 1 미만이어야 함 (>=1 또는 <0은 ERROR)"); r += 1

ROW_FIXED_VAR_C = r
label(sc, r, 2, "Fixed-Amount Variable Cost (F)")
input_cell(sc, r, 3, 1000, fmt='#,##0')
label(sc, r, 4, "variable_selling_delivery 중 금액형 항목 합계 (product_service_direct_cost 제외)"); r += 1

ROW_NET_SALES_FEE_C = r
label(sc, r, 2, "Net-Sales Fee Rate (b)")
input_cell(sc, r, 3, 0.10, fmt="0.0%")
label(sc, r, 4, "rate_of_net_sales 합계 — N에 곱함. 없으면 0"); r += 1

ROW_GROSS_PAYMENT_FEE_C = r
label(sc, r, 2, "Gross-Payment Fee Rate (a)")
input_cell(sc, r, 3, 0.03, fmt="0.0%")
label(sc, r, 4, "rate_of_gross_payment 합계 — G에 곱함. 없으면 0"); r += 1

ROW_ACTUAL_DIRECT_C = r
label(sc, r, 2, "Actual Direct Cost")
input_cell(sc, r, 3, 50000, fmt='#,##0')
label(sc, r, 4, "실제 product_service_direct_cost 합계 — ADC 계산에 절대 사용되지 않음(dependency isolation)"); r += 1

ROW_VCS = r
label(sc, r, 2, "Variable Cost Allocation Status (Excel simulation control — not a schema field)")
input_cell(sc, r, 3, "none")
label(sc, r, 4, (
    "Excel-only. F/b/a(변동비)의 공유비용 배부 상태 시뮬레이션. none=정상 계산 / "
    "unresolved=배부 미구현(ADC/gap/CM/CMR까지 전부 UNKNOWN) / invalid=shared+direct 모순(전부 ERROR)."
), wrap=True); r += 1

ROW_DCS = r
label(sc, r, 2, "Direct Cost Allocation Status (Excel simulation control — not a schema field)")
input_cell(sc, r, 3, "none")
label(sc, r, 4, (
    "Excel-only. actual_direct_cost만의 공유비용 배부 상태 시뮬레이션 — F/b/a와 완전히 분리된 컨트롤. "
    "none=정상 / unresolved=배부 미구현(actual_direct_cost·gap만 UNKNOWN) / invalid=모순(둘 다 ERROR). "
    "ADC·expected_contribution_margin(_rate)은 이 값과 무관하게 절대 변하지 않아야 함(가장 중요한 "
    "dependency-isolation 테스트, SPEC.md §9)."
), wrap=True); r += 2

REFS_C = {
    "p": f"$C${ROW_TARGET_MARKET_PRICE}", "incvat": f"$C${ROW_INCLUDES_VAT_C}",
    "v": f"$C${ROW_VAT_RATE_C}", "t": f"$C${ROW_TARGET_CM_C}",
    "f": f"$C${ROW_FIXED_VAR_C}", "b": f"$C${ROW_NET_SALES_FEE_C}", "a": f"$C${ROW_GROSS_PAYMENT_FEE_C}",
    "actual": f"$C${ROW_ACTUAL_DIRECT_C}", "vcs": f"$C${ROW_VCS}", "dcs": f"$C${ROW_DCS}",
}

section_row(sc, r, "RESULT (계산값 — 직접 입력 금지)", span=2); r += 1

RESULT_ROWS_C = {}
for key in METRIC_KEYS_C:
    RESULT_ROWS_C[key] = r
    r += 1
# hidden helper rows for _t_eff/_f_eff/_b_eff/_a_eff — column J, reused by the parity sheet's
# per-case column layout via a fresh cell_map each time (not shared cells).
HELPER_ROW_C = r
r += 1

result_cell_map_c = {key: (RESULT_ROWS_C[key], 3) for key in METRIC_KEYS_C}
result_cell_map_c["_t_eff"] = (HELPER_ROW_C, 10)
result_cell_map_c["_f_eff"] = (HELPER_ROW_C, 11)
result_cell_map_c["_b_eff"] = (HELPER_ROW_C, 12)
result_cell_map_c["_a_eff"] = (HELPER_ROW_C, 13)
for col_idx in (10, 11, 12, 13):
    sc.column_dimensions[get_column_letter(col_idx)].hidden = True
RESULT_CELLS_C = build_mode_c_formulas(sc, result_cell_map_c, REFS_C)

result_notes_c = {
    "market_net_sales_ex_vat": "N — price_includes_vat=FALSE→시장가 그대로 / TRUE→÷(1+v)",
    "market_gross_payment_incl_vat": "G — price_includes_vat=TRUE→시장가 그대로 / FALSE→×(1+v)",
    "allowable_direct_cost": "ADC = N×(1−t−b) − a×G − F (a=0이면 G 참조 안 함)",
    "actual_direct_cost": "실제 직접원가 — ADC와 완전히 독립 (Direct Cost Allocation Status만 영향)",
    "direct_cost_gap": "= ADC − Actual Direct Cost. 양수=여유, 음수=초과",
    "expected_contribution_margin": "= N − ADC − F − b×N − a×G (역산식과 독립적인 비용구조 재계산)",
    "expected_contribution_margin_rate": "= CM / N. N=0이면 ERROR(미입력이 아니라 계산불가)",
}
for key in METRIC_KEYS_C:
    row = RESULT_ROWS_C[key]
    label(sc, row, 2, METRIC_LABELS_C[key])
    fmt = "0.00%" if key == "expected_contribution_margin_rate" else '#,##0.00'
    c = sc.cell(row=row, column=3)
    c.font = value_font
    c.border = box
    c.alignment = Alignment(vertical="center", horizontal="right")
    c.number_format = fmt
    label(sc, row, 4, result_notes_c[key])
    coord = c.coordinate
    sc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="ERROR"'], fill=PatternFill("solid", fgColor=RED_BG)))
    sc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="UNKNOWN"'], fill=PatternFill("solid", fgColor=YELLOW)))
    sc.conditional_formatting.add(coord, FormulaRule(formula=[f'ISNUMBER({coord})'], fill=PatternFill("solid", fgColor=GREEN_BG)))
r += 1

ROW_NEGATIVE_ADC_NOTE = r
label(sc, r, 2, "Negative ADC?")
neg_formula = f'=IF(ISNUMBER({RESULT_CELLS_C["allowable_direct_cost"]}),IF({RESULT_CELLS_C["allowable_direct_cost"]}<0,"YES — NEGATIVE_ALLOWABLE_COST (경고, ERROR 아님)","NO"),"N/A")'
nc = formula_cell(sc, r, 3, neg_formula, fmt="General", bold=False)
sc.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
nc.alignment = Alignment(horizontal="left")
sc.conditional_formatting.add(nc.coordinate, FormulaRule(formula=[f'LEFT({nc.coordinate},3)="YES"'], fill=PatternFill("solid", fgColor=YELLOW)))
r += 1

ROW_SELF_CHECK_C = r
label(sc, r, 2, "Self-Check: |CMR − t| ≤ 0.0001?")
selfcheck_cell_c = build_self_check_cell(sc, r, 3, RESULT_CELLS_C["expected_contribution_margin_rate"], REFS_C["t"])
sc_cell_obj_c = sc.cell(row=r, column=3)
sc_cell_obj_c.font = value_font
sc_cell_obj_c.border = box
sc_cell_obj_c.alignment = Alignment(vertical="center", horizontal="right")
label(sc, r, 4, (
    "expected_contribution_margin은 t×N이 아니라 비용구조(N-ADC-F-bN-aG)로 독립 재계산됩니다. "
    "그 결과로 얻은 CMR(=CM/N)이 목표 t와 tolerance 내에서 일치하는지 진단하는 별도 셀. "
    "MODE C의 공식 출력 metric은 아님 — 산술 오류를 잡기 위한 진단용."
), wrap=True)
sc.conditional_formatting.add(selfcheck_cell_c, FormulaRule(formula=[f'{selfcheck_cell_c}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
sc.conditional_formatting.add(selfcheck_cell_c, FormulaRule(formula=[f'{selfcheck_cell_c}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
r += 1

section_row(sc, r, "STATUS", span=2); r += 1
ROW_STATUS_C = r
# Canonical 3-tier (dependency_rules.md section 5): ERROR > INCOMPLETE > OK. NEGATIVE_ALLOWABLE_COST
# is a non-blocking warning on a numeric ADC value -- it never appears as ERROR/UNKNOWN text in
# any of these 7 cells, so it can never drag Overall Status down (verified by TC11 in 07_MODE_C_PARITY_TEST).
status_metric_cells_c = [RESULT_CELLS_C[k] for k in METRIC_KEYS_C]
error_check_c = "+".join(f'IF({cell}="ERROR",1,0)' for cell in status_metric_cells_c)
unknown_check_c = "+".join(f'IF({cell}="UNKNOWN",1,0)' for cell in status_metric_cells_c)
status_formula_c = (
    f'=IF(({error_check_c})>0,"ERROR — 목표 불가능 또는 입력값 모순",'
    f'IF(({unknown_check_c})>0,"INCOMPLETE — 일부 지표 UNKNOWN","OK — 전체 계산 완료"))'
)
label(sc, r, 2, "Overall Status")
stc = formula_cell(sc, r, 3, status_formula_c, fmt="General")
sc.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
stc.alignment = Alignment(horizontal="left")
r += 1

label(sc, r, 2, "blank = UNKNOWN / 0 = explicit zero", italic=True)
r += 2

# ---- DASHBOARD CARD ----
section_row(sc, r, "DASHBOARD CARD", span=5); r += 1
card_top = r
cards_c = [
    ("Market Net Sales (N)", RESULT_CELLS_C["market_net_sales_ex_vat"], '#,##0'),
    ("Allowable Direct Cost", RESULT_CELLS_C["allowable_direct_cost"], '#,##0'),
    ("Actual Direct Cost", RESULT_CELLS_C["actual_direct_cost"], '#,##0'),
    ("Direct Cost Gap", RESULT_CELLS_C["direct_cost_gap"], '#,##0'),
    ("Expected CM", RESULT_CELLS_C["expected_contribution_margin"], '#,##0'),
    ("Expected CM Rate", RESULT_CELLS_C["expected_contribution_margin_rate"], "0.0%"),
]
card_w, gap = 2, 1
col = 2
for i, (label_txt, ref, fmt) in enumerate(cards_c):
    if i == 3:
        col = 2
        card_top = r + 3
    cr = card_top
    sc.merge_cells(start_row=cr, start_column=col, end_row=cr, end_column=col + card_w - 1)
    lc = sc.cell(row=cr, column=col, value=label_txt)
    lc.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    lc.fill = PatternFill("solid", fgColor=NAVY)
    lc.alignment = Alignment(horizontal="center", vertical="center")
    sc.merge_cells(start_row=cr + 1, start_column=col, end_row=cr + 1, end_column=col + card_w - 1)
    vc = sc.cell(row=cr + 1, column=col, value=f"={ref}")
    vc.font = Font(name="Calibri", size=16, bold=True, color=INK)
    vc.number_format = fmt
    vc.fill = PatternFill("solid", fgColor=LIGHT)
    vc.alignment = Alignment(horizontal="center", vertical="center")
    vc.border = box
    sc.row_dimensions[cr + 1].height = 26
    vcoord = vc.coordinate
    sc.conditional_formatting.add(vcoord, FormulaRule(formula=[f"NOT(ISNUMBER({vcoord}))"], fill=PatternFill("solid", fgColor=RED_BG)))
    sc.conditional_formatting.add(vcoord, FormulaRule(formula=[f"ISNUMBER({vcoord})"], fill=PatternFill("solid", fgColor=GREEN_BG)))
    col += card_w + gap

sc.freeze_panes = "B4"
dv_c = DataValidation(type="list", formula1='"TRUE,FALSE"', allow_blank=True)
sc.add_data_validation(dv_c)
dv_c.add(sc.cell(row=ROW_INCLUDES_VAT_C, column=3))

dv_vcs = DataValidation(type="list", formula1='"none,unresolved,invalid"', allow_blank=False)
sc.add_data_validation(dv_vcs)
dv_vcs.add(sc.cell(row=ROW_VCS, column=3))

dv_dcs = DataValidation(type="list", formula1='"none,unresolved,invalid"', allow_blank=False)
sc.add_data_validation(dv_dcs)
dv_dcs.add(sc.cell(row=ROW_DCS, column=3))
print("06_MODE_C_SIMULATOR_OK")

# ================================================================
# SHEET: 07_MODE_C_PARITY_TEST
# ================================================================
pc = wb.create_sheet("07_MODE_C_PARITY_TEST")
pc.sheet_view.showGridLines = False
pc.column_dimensions["A"].width = 2
pc.column_dimensions["B"].width = 34
for col in "CDEFG":
    pc.column_dimensions[col].width = 16
pc.column_dimensions["H"].width = 10

r = 2
title_row(pc, r, "07. Python Engine vs Excel Formula — MODE C Parity Test", span=6); r += 1
pc.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
c = pc.cell(row=r, column=2, value=(
    "각 케이스는 docs/features/mode_c_allowable_cost/CASE.md의 TC1-20에 대응하며, Excel에 동일 입력값을 "
    "리터럴로 심어 06_MODE_C_SIMULATOR와 같은 수식(build_mode_c_formulas)으로 독립 재계산하고, Python "
    "참조값(core/engine/modes/mode_c.py 실행 결과, 빌드 시점에 고정)과 비교합니다. 허용오차 0.01(금액) / "
    "0.0001(비율). TC14/TC15/TC18은 Variable Cost Allocation Status로, TC20은 Direct Cost Allocation "
    "Status로 공유비용 배부 미구현/모순 상태를 시뮬레이션합니다 — TC19/TC20은 특히 Direct Cost Allocation "
    "Status를 바꿔도 allowable_direct_cost/expected_contribution_margin(_rate)이 전혀 영향받지 않는지를 "
    "실시간으로 검증하는, 가장 중요한 dependency-isolation 케이스입니다. 20개 전부 live Excel evaluation."
))
c.font = note_font
c.alignment = Alignment(wrap_text=True, vertical="top")
pc.row_dimensions[r].height = 56
r += 2

TOL_AMOUNT_C = 0.01
TOL_RATE_C = 0.0001
RATE_METRICS_C = {"expected_contribution_margin_rate"}
FIELD_ORDER_C = ["target_market_price", "includes_vat", "vat_rate", "target_cm_rate",
                  "fixed_variable_cost", "net_sales_fee_rate", "gross_payment_fee_rate",
                  "actual_direct_cost", "vcs", "dcs"]

# All numeric fields default to explicit 0 (never bare None) unless a scenario is specifically
# testing UNKNOWN propagation — matching CASE.md's null != 0 principle. vcs/dcs default to "none".
PARITY_CASES_C = [
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

for case in PARITY_CASES_C:
    ci_kwargs = {k: v for k, v in case.items() if k not in ("name", "vcs", "dcs", "extra_cost_items")}
    ci_kwargs["extra_cost_items"] = case.get("extra_cost_items")
    ci = make_client_input_c(**ci_kwargs)
    result = run_mode_c(ci)
    m = result["per_component"]["main"]
    case["python_result"] = {k: (m[k]["value"] if m[k]["status"] == "OK" else m[k]["status"]) for k in METRIC_KEYS_C}

overall_pass_cells_c = []

for case in PARITY_CASES_C:
    section_row(pc, r, case["name"], span=5); r += 1
    for i, h in enumerate(["Metric", "Excel Result", "Python Reference", "Difference", "PASS / FAIL"]):
        cc = pc.cell(row=r, column=2 + i, value=h)
        cc.font = header_font
        cc.fill = header_fill
        cc.alignment = Alignment(horizontal="center")
    r += 1

    input_col = 9
    local_row = r
    li = {}
    for j, field in enumerate(FIELD_ORDER_C):
        val = case[field]
        cell = pc.cell(row=local_row, column=input_col + j, value=val)
        li[field] = f"${get_column_letter(input_col + j)}${local_row}"
    result_col_start = input_col + len(FIELD_ORDER_C)
    for col_idx in range(input_col, result_col_start + len(METRIC_KEYS_C) + 4):
        pc.column_dimensions[get_column_letter(col_idx)].hidden = True

    refs_local = {
        "p": li["target_market_price"], "incvat": li["includes_vat"], "v": li["vat_rate"],
        "t": li["target_cm_rate"], "f": li["fixed_variable_cost"], "b": li["net_sales_fee_rate"],
        "a": li["gross_payment_fee_rate"], "actual": li["actual_direct_cost"],
        "vcs": li["vcs"], "dcs": li["dcs"],
    }
    cell_map_local = {key: (local_row, result_col_start + i) for i, key in enumerate(METRIC_KEYS_C)}
    cell_map_local["_t_eff"] = (local_row, result_col_start + len(METRIC_KEYS_C))
    cell_map_local["_f_eff"] = (local_row, result_col_start + len(METRIC_KEYS_C) + 1)
    cell_map_local["_b_eff"] = (local_row, result_col_start + len(METRIC_KEYS_C) + 2)
    cell_map_local["_a_eff"] = (local_row, result_col_start + len(METRIC_KEYS_C) + 3)
    excel_cell_for = build_mode_c_formulas(pc, cell_map_local, refs_local)

    for mk in METRIC_KEYS_C:
        label(pc, r, 2, METRIC_LABELS_C[mk])
        excel_ref = excel_cell_for[mk]
        fmt = "0.00%" if mk in RATE_METRICS_C else '#,##0.00'
        formula_cell(pc, r, 3, f"={excel_ref}", fmt=fmt, bold=False)

        py_val = case["python_result"][mk]
        pcv = pc.cell(row=r, column=4, value=py_val)
        pcv.border = box
        pcv.alignment = Alignment(horizontal="right")
        if isinstance(py_val, (int, float)):
            pcv.number_format = fmt

        tol = TOL_RATE_C if mk in RATE_METRICS_C else TOL_AMOUNT_C
        py_cell = pcv.coordinate
        diff_f = f'=IF(ISNUMBER({py_cell}),IF(ISNUMBER({excel_ref}),ABS({excel_ref}-{py_cell}),"N/A"),"N/A")'
        formula_cell(pc, r, 5, diff_f, fmt='0.0000', bold=False)

        # Nested IF rather than AND(...): Excel's AND evaluates every argument eagerly (no
        # short-circuit), so AND(ISNUMBER(x), ABS(x-y)<=tol) raises a raw #VALUE! the moment x is
        # text — even though the ISNUMBER(x) guard is meant to prevent exactly that subtraction.
        pass_f = (
            f'=IFERROR(IF(ISNUMBER({py_cell}),'
            f'IF(ISNUMBER({excel_ref}),IF(ABS({excel_ref}-{py_cell})<={tol},"PASS","FAIL"),"FAIL"),'
            f'IF(NOT(ISNUMBER({excel_ref})),IF({excel_ref}={py_cell},"PASS","FAIL"),"FAIL")),"FAIL")'
        )
        pcell = formula_cell(pc, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells_c.append(pcell.coordinate)
        pc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
        pc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
        r += 1
    r += 1

section_row(pc, r, "Overall (all 20 scenarios — TC1-20, all live Excel evaluation)", span=2); r += 1
label(pc, r, 2, "All metrics PASS?")
overall_f_c = f'=IF(COUNTIF({overall_pass_cells_c[0]}:{overall_pass_cells_c[-1]},"FAIL")=0,"ALL PASS","SOME FAILED")'
oc_c = formula_cell(pc, r, 3, overall_f_c, fmt="General", bold=True)
pc.conditional_formatting.add(oc_c.coordinate, FormulaRule(formula=[f'{oc_c.coordinate}="SOME FAILED"'], fill=PatternFill("solid", fgColor=RED_BG)))
pc.conditional_formatting.add(oc_c.coordinate, FormulaRule(formula=[f'{oc_c.coordinate}="ALL PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))

pc.freeze_panes = "B4"
print("07_MODE_C_PARITY_TEST_OK")

# ================================================================
# SHEET: 08_BEP_SIMULATOR
# ================================================================
from core.engine.modes.bep import run_bep  # noqa: E402
from scenario_helpers import make_client_input_bep, METRIC_KEYS_BEP, METRIC_LABELS_BEP  # noqa: E402

sbep = wb.create_sheet("08_BEP_SIMULATOR")
sbep.sheet_view.showGridLines = False
sbep.column_dimensions["A"].width = 2
sbep.column_dimensions["B"].width = 34
sbep.column_dimensions["C"].width = 16
sbep.column_dimensions["D"].width = 50

r = 2
title_row(sbep, r, "08. BEP Simulator — Break-Even Point (Interactive)", span=3); r += 2

section_row(sbep, r, "INPUT (노란 셀만 입력, 단일 컴포넌트 기준)", span=2); r += 1

ROW_ACTUAL_PRICE_BEP = r
label(sbep, r, 2, "Actual Price")
input_cell(sbep, r, 3, 20000, fmt='#,##0')
label(sbep, r, 4, "현재 실제 판매가격 — BEP는 항상 current price 기준 (MODE B/C 가격 대입 안 함)"); r += 1

ROW_INCLUDES_VAT_BEP = r
label(sbep, r, 2, "Price Includes VAT")
input_cell(sbep, r, 3, False)
label(sbep, r, 4, "TRUE=판매가에 VAT 포함 / FALSE=별도 / 빈칸=모름"); r += 1

ROW_VAT_RATE_BEP = r
label(sbep, r, 2, "VAT Rate (v)")
input_cell(sbep, r, 3, 0.10, fmt="0.0%")
label(sbep, r, 4, "a=0이면 CMu 계산에 불필요"); r += 1

ROW_DIRECT_BEP = r
label(sbep, r, 2, "Product/Service Direct Cost")
input_cell(sbep, r, 3, 8000, fmt='#,##0')
label(sbep, r, 4, "CMu 계산에만 사용 (fixed_operating_cost와 무관)"); r += 1

ROW_VARFIXED_BEP = r
label(sbep, r, 2, "Variable Selling/Delivery Cost (Fixed Amount)")
input_cell(sbep, r, 3, 2000, fmt='#,##0')
label(sbep, r, 4, "variable_selling_delivery 중 금액형 항목 합계"); r += 1

ROW_RATENET_BEP = r
label(sbep, r, 2, "Net-Sales Fee Rate (b)")
input_cell(sbep, r, 3, 0, fmt="0.0%")
label(sbep, r, 4, "rate_of_net_sales 합계 — N에 곱함. 없으면 0"); r += 1

ROW_RATEGROSS_BEP = r
label(sbep, r, 2, "Gross-Payment Fee Rate (a)")
input_cell(sbep, r, 3, 0, fmt="0.0%")
label(sbep, r, 4, "rate_of_gross_payment 합계 — G에 곱함. 없으면 0"); r += 1

ROW_FC_AMOUNT_BEP = r
label(sbep, r, 2, "Fixed Operating Cost Amount")
input_cell(sbep, r, 3, 1000000, fmt='#,##0')
label(sbep, r, 4, "Fixed Cost Allocation Status=component일 때만 사용"); r += 1

ROW_FC_BASIS_BEP = r
label(sbep, r, 2, "Fixed Operating Cost Basis")
input_cell(sbep, r, 3, "per_month")
label(sbep, r, 4, "analysis period context (예: per_month) — quantity unit이 아님. break_even_quantity_exact.unit은 항상 \"units\""); r += 1

ROW_FCS_BEP = r
label(sbep, r, 2, "Fixed Cost Allocation Status (Excel simulation control — not a schema field)")
input_cell(sbep, r, 3, "component")
label(sbep, r, 4, (
    "Excel-only. none=fixed_operating_cost 항목 자체가 없음(FC 확정 0, basis 없음) / "
    "component=Fixed Operating Cost Amount/Basis 입력 사용 / unresolved=공유비용 배부 미구현"
    "(UNKNOWN) / blended_only=배부 대상 아님으로 설정(UNKNOWN, BEP만의 deviation — 다른 모드처럼 "
    "0으로 취급하지 않음) / invalid_direct=shared+direct 모순 설정(ERROR). "
    "실제 shared-cost 배부 엔진은 구현되지 않음 — 미지원 상태를 조용히 숫자로 만들지 않는지만 검증."
), wrap=True); r += 2

REFS_BEP = {
    "p": f"$C${ROW_ACTUAL_PRICE_BEP}", "incvat": f"$C${ROW_INCLUDES_VAT_BEP}",
    "v": f"$C${ROW_VAT_RATE_BEP}", "direct": f"$C${ROW_DIRECT_BEP}",
    "varfixed": f"$C${ROW_VARFIXED_BEP}", "ratenet": f"$C${ROW_RATENET_BEP}",
    "rategross": f"$C${ROW_RATEGROSS_BEP}", "fc": f"$C${ROW_FC_AMOUNT_BEP}",
    "fcbasis": f"$C${ROW_FC_BASIS_BEP}", "fcs": f"$C${ROW_FCS_BEP}",
}

section_row(sbep, r, "RESULT (계산값 — 직접 입력 금지)", span=2); r += 1

RESULT_ROWS_BEP = {}
for key in METRIC_KEYS_BEP:
    RESULT_ROWS_BEP[key] = r
    r += 1
ROW_ANALYSIS_BASIS_BEP = r
r += 1
HELPER_ROW_BEP = r  # hidden helper row for _n/_g/_diagnostic_code
r += 1

result_cell_map_bep = {key: (RESULT_ROWS_BEP[key], 3) for key in METRIC_KEYS_BEP}
result_cell_map_bep["analysis_period_basis"] = (ROW_ANALYSIS_BASIS_BEP, 3)
result_cell_map_bep["_n"] = (HELPER_ROW_BEP, 10)
result_cell_map_bep["_g"] = (HELPER_ROW_BEP, 11)
result_cell_map_bep["_diagnostic_code"] = (HELPER_ROW_BEP, 12)
for col_idx in (10, 11, 12):
    sbep.column_dimensions[get_column_letter(col_idx)].hidden = True
RESULT_CELLS_BEP = build_bep_formulas(sbep, result_cell_map_bep, REFS_BEP)

result_notes_bep = {
    "contribution_margin_per_unit": "CMu = N − direct − varfixed − b×N − a×G (a=0이면 G 참조 안 함)",
    "fixed_operating_cost": "FC — Fixed Cost Allocation Status에 따라 결정",
    "break_even_quantity_exact": "Q_BEP = FC / CMu. CMu<=0이면 NOT_APPLICABLE (0/음수 출력 안 함)",
}
for key in METRIC_KEYS_BEP:
    row = RESULT_ROWS_BEP[key]
    label(sbep, row, 2, METRIC_LABELS_BEP[key])
    c = sbep.cell(row=row, column=3)
    c.font = value_font
    c.border = box
    c.alignment = Alignment(vertical="center", horizontal="right")
    c.number_format = '#,##0.00'
    label(sbep, row, 4, result_notes_bep[key])
    coord = c.coordinate
    sbep.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="ERROR"'], fill=PatternFill("solid", fgColor=RED_BG)))
    sbep.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="UNKNOWN"'], fill=PatternFill("solid", fgColor=YELLOW)))
    sbep.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="NOT_APPLICABLE"'], fill=PatternFill("solid", fgColor=YELLOW)))
    sbep.conditional_formatting.add(coord, FormulaRule(formula=[f'ISNUMBER({coord})'], fill=PatternFill("solid", fgColor=GREEN_BG)))

# NOTE: build_bep_formulas() already wrote the analysis_period_basis formula directly into
# (ROW_ANALYSIS_BASIS_BEP, 3) via result_cell_map_bep above — only add the label/formatting here,
# writing a second formula into the same cell would self-reference it.
label(sbep, ROW_ANALYSIS_BASIS_BEP, 2, "Analysis Period Basis")
abc = sbep.cell(row=ROW_ANALYSIS_BASIS_BEP, column=3)
abc.font = value_font
abc.border = box
abc.alignment = Alignment(vertical="center", horizontal="right")
label(sbep, ROW_ANALYSIS_BASIS_BEP, 4, (
    "fixed_operating_cost가 정의된 기간 context — quantity unit이 아님. 빈칸=해당 항목 없음/UNKNOWN/ERROR."
))
r += 1

ROW_SELF_CHECK_BEP = r
label(sbep, r, 2, "Self-Check: |Q_BEP × CMu − FC| ≤ tolerance?")
q_cell_bep = RESULT_CELLS_BEP["break_even_quantity_exact"]
cmu_cell_bep = RESULT_CELLS_BEP["contribution_margin_per_unit"]
fc_cell_bep = RESULT_CELLS_BEP["fixed_operating_cost"]
selfcheck_formula_bep = (
    f'=IF(NOT(ISNUMBER({q_cell_bep})),"N/A — Q_BEP not numeric (UNKNOWN/ERROR/NOT_APPLICABLE)",'
    f'IF(ABS({q_cell_bep}*{cmu_cell_bep}-{fc_cell_bep})<=0.01,"PASS","FAIL"))'
)
sc_bep = formula_cell(sbep, r, 3, selfcheck_formula_bep, fmt="General", bold=False)
sc_bep.alignment = Alignment(horizontal="left")
label(sbep, r, 4, (
    "Python 출력을 그대로 복사하지 않고, Q_BEP×CMu가 독립적으로 FC와 tolerance 내 일치하는지 "
    "역산 검증하는 진단 셀. CMu<=0(NOT_APPLICABLE)이거나 UNKNOWN/ERROR면 N/A."
), wrap=True)
sbep.conditional_formatting.add(sc_bep.coordinate, FormulaRule(formula=[f'{sc_bep.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
sbep.conditional_formatting.add(sc_bep.coordinate, FormulaRule(formula=[f'{sc_bep.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
r += 1

section_row(sbep, r, "STATUS", span=2); r += 1
ROW_STATUS_BEP = r
status_metric_cells_bep = [RESULT_CELLS_BEP[k] for k in METRIC_KEYS_BEP]
error_check_bep = "+".join(f'IF({cell}="ERROR",1,0)' for cell in status_metric_cells_bep)
unknown_check_bep = "+".join(f'IF({cell}="UNKNOWN",1,0)' for cell in status_metric_cells_bep)
status_formula_bep = (
    f'=IF(({error_check_bep})>0,"ERROR — 계산 불가 또는 입력값 모순",'
    f'IF(({unknown_check_bep})>0,"INCOMPLETE — 일부 지표 UNKNOWN","OK — 전체 계산 완료 (NOT_APPLICABLE 포함 가능)"))'
)
label(sbep, r, 2, "Overall Status")
stc_bep = formula_cell(sbep, r, 3, status_formula_bep, fmt="General")
sbep.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
stc_bep.alignment = Alignment(horizontal="left")
r += 1
label(sbep, r, 2, (
    "blank = UNKNOWN / 0 = explicit zero / NOT_APPLICABLE ≠ ERROR·UNKNOWN (module status를 낮추지 않음)"
), italic=True)
r += 2

# ---- DASHBOARD CARD ----
section_row(sbep, r, "DASHBOARD CARD", span=5); r += 1
card_top = r
cards_bep = [
    ("Contribution Margin per Unit", RESULT_CELLS_BEP["contribution_margin_per_unit"], '#,##0'),
    ("Fixed Operating Cost", RESULT_CELLS_BEP["fixed_operating_cost"], '#,##0'),
    ("Break-Even Quantity", RESULT_CELLS_BEP["break_even_quantity_exact"], '#,##0.00'),
]
card_w, gap = 3, 1
col = 2
for label_txt, ref, fmt in cards_bep:
    cr = card_top
    sbep.merge_cells(start_row=cr, start_column=col, end_row=cr, end_column=col + card_w - 1)
    lc = sbep.cell(row=cr, column=col, value=label_txt)
    lc.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    lc.fill = PatternFill("solid", fgColor=NAVY)
    lc.alignment = Alignment(horizontal="center", vertical="center")
    sbep.merge_cells(start_row=cr + 1, start_column=col, end_row=cr + 1, end_column=col + card_w - 1)
    vc = sbep.cell(row=cr + 1, column=col, value=f"={ref}")
    vc.font = Font(name="Calibri", size=16, bold=True, color=INK)
    vc.number_format = fmt
    vc.fill = PatternFill("solid", fgColor=LIGHT)
    vc.alignment = Alignment(horizontal="center", vertical="center")
    vc.border = box
    sbep.row_dimensions[cr + 1].height = 26
    vcoord = vc.coordinate
    sbep.conditional_formatting.add(vcoord, FormulaRule(formula=[f"NOT(ISNUMBER({vcoord}))"], fill=PatternFill("solid", fgColor=RED_BG)))
    sbep.conditional_formatting.add(vcoord, FormulaRule(formula=[f"ISNUMBER({vcoord})"], fill=PatternFill("solid", fgColor=GREEN_BG)))
    col += card_w + gap

sbep.freeze_panes = "B4"
dv_bep_vat = DataValidation(type="list", formula1='"TRUE,FALSE"', allow_blank=True)
sbep.add_data_validation(dv_bep_vat)
dv_bep_vat.add(sbep.cell(row=ROW_INCLUDES_VAT_BEP, column=3))

dv_fcs = DataValidation(type="list", formula1='"none,component,unresolved,blended_only,invalid_direct"', allow_blank=False)
sbep.add_data_validation(dv_fcs)
dv_fcs.add(sbep.cell(row=ROW_FCS_BEP, column=3))
print("08_BEP_SIMULATOR_OK")

# ================================================================
# SHEET: 09_BEP_PARITY_TEST
# ================================================================
pbep = wb.create_sheet("09_BEP_PARITY_TEST")
pbep.sheet_view.showGridLines = False
pbep.column_dimensions["A"].width = 2
pbep.column_dimensions["B"].width = 34
for col in "CDEFG":
    pbep.column_dimensions[col].width = 16
pbep.column_dimensions["H"].width = 10

r = 2
title_row(pbep, r, "09. Python Engine vs Excel Formula — BEP Parity Test", span=6); r += 1
pbep.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
c = pbep.cell(row=r, column=2, value=(
    "각 케이스는 docs/features/bep/CASE.md의 TC1-23에 대응하며(+ TC24-26은 basis 불일치/NOT_APPLICABLE/"
    "multi-component 우선순위 보강 케이스), Excel에 동일 입력값을 리터럴로 심어 08_BEP_SIMULATOR와 같은 "
    "수식(build_bep_formulas)으로 독립 재계산하고, Python 참조값(core/engine/modes/bep.py 실행 결과, 빌드 "
    "시점에 고정)과 비교합니다. 허용오차 0.01. TC14/TC15/TC24는 Fixed Cost Allocation Status/Basis "
    "Consistency 컨트롤로, TC18/TC19/TC26은 Component Count 컨트롤로 시뮬레이션합니다. 26개 중 25개가 "
    "live Excel evaluation입니다 — TC13(통화 미지원)만 08_BEP_SIMULATOR에 항목별 통화 입력이 없어(MODE "
    "A/B/C Excel Simulator와 동일한 단순화) reference-only(00_GUIDE의 Hybrid HW+SaaS 블록과 동일 패턴)로 "
    "표시됩니다. Q_BEP가 숫자일 때는 Self-Check(|Q_BEP×CMu−FC|<=tol)로 Python 값을 그대로 복사하지 "
    "않았음을 독립 검증합니다."
))
c.font = note_font
c.alignment = Alignment(wrap_text=True, vertical="top")
pbep.row_dimensions[r].height = 68
r += 2

TOL_AMOUNT_BEP = 0.01
FIELD_ORDER_BEP = ["actual_price", "includes_vat", "vat_rate", "direct", "varfixed", "ratenet",
                   "rategross", "fc", "fcbasis", "fcs", "fbc", "cc"]

PARITY_CASES_BEP = [
    dict(name="TC1. Simple positive CM",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC2. Fixed cost = 0 (explicit)",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=0, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC3. No fixed-cost item at all",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="", fcs="none", fbc="consistent", cc=1),
    dict(name="TC4. Fixed-cost item exists, amount null",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC5. CM = 0, FC > 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=600, varfixed=400,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC6. CM < 0, FC > 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=700, varfixed=400,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC7. VAT-inclusive display",
         actual_price=1100, includes_vat=True, vat_rate=0.10, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC8. VAT-exclusive display, same economics as TC7",
         actual_price=1000, includes_vat=False, vat_rate=0.10, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC9. Net-sales fee",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=200, varfixed=0,
         ratenet=0.1, rategross=0, fc=70000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC10. Gross-payment fee",
         actual_price=1000, includes_vat=False, vat_rate=0.10, direct=0, varfixed=0,
         ratenet=0, rategross=0.05, fc=94500, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC11. v UNKNOWN, not needed (a=0)",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=300, varfixed=0,
         ratenet=0.1, rategross=0, fc=60000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC12. v UNKNOWN, required",
         actual_price=1100, includes_vat=True, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC13. Unsupported currency on FC item",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1,
         fc_currency="EUR"),
    dict(name="TC14. Shared fixed cost, unresolved",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="per_month", fcs="unresolved", fbc="consistent", cc=1),
    dict(name="TC15. Shared + direct invalid configuration",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="per_month", fcs="invalid_direct", fbc="consistent", cc=1),
    dict(name="TC16. Explicit zero rate",
         actual_price=1000, includes_vat=False, vat_rate=0.10, direct=400, varfixed=0,
         ratenet=0, rategross=0.05, fc=60000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC17. Non-integer break-even quantity",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=52340, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC18. Multi-component, component-specific FC (refused)",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=2),
    dict(name="TC19. Multi-component + shared FC (still refused)",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=None, fcbasis="per_month", fcs="blended_only", fbc="consistent", cc=2),
    dict(name="TC20. CM input UNKNOWN (direct cost missing), FC isolated",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=None, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC21. FC = 0, CM = 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=600, varfixed=400,
         ratenet=0, rategross=0, fc=0, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC22. FC = 0, CM < 0",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=700, varfixed=400,
         ratenet=0, rategross=0, fc=0, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC23. Negative fixed-cost amount",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=-10000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC24. Inconsistent fixed-cost basis",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="inconsistent", cc=1),
    dict(name="TC25. NOT_APPLICABLE keeps module status OK",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=700, varfixed=400,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="consistent", cc=1),
    dict(name="TC26. Multi-component gate beats basis-inconsistency error",
         actual_price=1000, includes_vat=False, vat_rate=None, direct=400, varfixed=100,
         ratenet=0, rategross=0, fc=50000, fcbasis="per_month", fcs="component", fbc="inconsistent", cc=2),
]


def _bep_python_reference(case):
    """Builds the equivalent Client Input and runs bep.py — mirrors what the Excel case's
    literal inputs express, including the fcs/fbc/cc Excel-only controls' Python-side meaning."""
    extra_components = None
    if case["cc"] > 1:
        extra_components = [{
            "component_id": "addon", "type": "one_time", "actual_price": 500,
            "currency": "KRW", "price_includes_vat": False,
        }]

    if case["fcs"] == "none":
        fc_value = False  # make_client_input_bep: omit the FC item entirely
        extra_fc_items = None
    elif case["fcs"] == "component":
        fc_value = case["fc"]
        extra_fc_items = None
        if case.get("fc_currency"):
            # Override: replace the default fc item with one carrying an unsupported currency.
            fc_value = False
            extra_fc_items = [{
                "item_id": "fixed_ops", "label": "고정운영비", "cost_category": "fixed_operating_cost",
                "amount": case["fc"], "rate": None, "currency": case["fc_currency"],
                "basis": case["fcbasis"], "applies_to_component": "main",
            }]
        if case["fbc"] == "inconsistent":
            fc_value = case["fc"]
            extra_fc_items = [{
                "item_id": "fixed_ops_2", "label": "고정운영비(다른 기간)", "cost_category": "fixed_operating_cost",
                "amount": 20000, "rate": None, "currency": "KRW", "basis": "per_visit",
                "applies_to_component": "main",
            }]
    else:
        fc_value = None  # item exists (present), value irrelevant — allocation_rule drives status
        allocation_rule = {"unresolved": "by_component_revenue", "blended_only": "blended_only",
                            "invalid_direct": "direct"}[case["fcs"]]
        extra_fc_items = None
        fc_value = False
        extra_fc_items = [{
            "item_id": "fixed_ops_shared", "label": "공유 고정운영비", "cost_category": "fixed_operating_cost",
            "amount": None, "rate": None, "currency": None, "basis": case["fcbasis"] or "per_month",
            "applies_to_component": "shared", "allocation_rule": allocation_rule,
        }]

    ci = make_client_input_bep(
        actual_price=case["actual_price"], includes_vat=case["includes_vat"], vat_rate=case["vat_rate"],
        direct_cost=case["direct"], variable_fixed_cost=case["varfixed"],
        net_sales_fee_rate=case["ratenet"], gross_payment_fee_rate=case["rategross"],
        fixed_operating_cost=fc_value, fixed_operating_cost_basis=case["fcbasis"] or "per_month",
        extra_cost_items=extra_fc_items, extra_components=extra_components,
    )
    result = run_bep(ci)
    if case["cc"] > 1:
        return {
            "contribution_margin_per_unit": "ERROR", "fixed_operating_cost": "ERROR",
            "break_even_quantity_exact": "ERROR", "analysis_period_basis": "",
        }, result["status"], "MULTI_COMPONENT_BEP_NOT_SUPPORTED"
    m = result["per_component"]["main"]
    py_metrics = {
        "contribution_margin_per_unit": m["contribution_margin_per_unit"]["value"] if m["contribution_margin_per_unit"]["status"] == "OK" else m["contribution_margin_per_unit"]["status"],
        "fixed_operating_cost": m["fixed_operating_cost"]["value"] if m["fixed_operating_cost"]["status"] == "OK" else m["fixed_operating_cost"]["status"],
        "break_even_quantity_exact": m["break_even_quantity_exact"]["value"] if m["break_even_quantity_exact"]["status"] == "OK" else m["break_even_quantity_exact"]["status"],
        "analysis_period_basis": m["analysis_period_basis"] if m["analysis_period_basis"] is not None else "",
    }
    primary_code = result["warnings"][0]["code"] if result["warnings"] else "NONE"
    return py_metrics, result["status"], primary_code


for case in PARITY_CASES_BEP:
    py_metrics, py_status, py_code = _bep_python_reference(case)
    case["python_result"] = py_metrics
    case["python_status"] = py_status
    case["python_code"] = py_code

overall_pass_cells_bep = []

for case in PARITY_CASES_BEP:
    is_reference_only = bool(case.get("fc_currency"))
    section_row(pbep, r, case["name"] + (" (REFERENCE ONLY)" if is_reference_only else ""), span=5); r += 1

    if is_reference_only:
        # 08_BEP_SIMULATOR's flat single-value inputs have no per-item currency field for
        # fixed_operating_cost (same simplification MODE A/B/C's Excel Simulators already make —
        # none of them model per-item currency variance either) — an "unsupported currency on
        # the FC item" scenario is therefore not expressible as a live Excel formula at all, only
        # as a Python-side reference value, mirroring 00_GUIDE's Hybrid HW+SaaS reference block.
        pbep.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
        note_cell = pbep.cell(row=r, column=2, value=(
            "08_BEP_SIMULATOR에는 fixed_operating_cost 항목별 통화(currency) 입력이 없음(MODE A/B/C "
            "Excel Simulator와 동일한 단순화) — 이 케이스는 live Excel 수식으로 표현 불가능하여 "
            "Python 참조값만 기록합니다(00_GUIDE의 Hybrid HW+SaaS 참고용 블록과 동일 패턴)."
        ))
        note_cell.font = note_font
        note_cell.alignment = Alignment(wrap_text=True, vertical="top")
        pbep.row_dimensions[r].height = 30
        r += 1
        for mk in METRIC_KEYS_BEP + ["analysis_period_basis"]:
            label(pbep, r, 2, METRIC_LABELS_BEP.get(mk, "Analysis Period Basis"))
            py_val = case["python_result"][mk]
            vcell = pbep.cell(row=r, column=3, value=py_val)
            vcell.border = box
            vcell.alignment = Alignment(horizontal="right")
            if isinstance(py_val, (int, float)):
                vcell.number_format = '#,##0.00'
            r += 1
        label(pbep, r, 2, "Module Status Tier (reference)")
        pbep.cell(row=r, column=3, value=case["python_status"]).border = box
        r += 1
        label(pbep, r, 2, "Primary Warning Code (reference)")
        pbep.cell(row=r, column=3, value=case["python_code"]).border = box
        r += 1
        r += 1
        continue

    for i, h in enumerate(["Metric", "Excel Result", "Python Reference", "Difference", "PASS / FAIL"]):
        cc_hdr = pbep.cell(row=r, column=2 + i, value=h)
        cc_hdr.font = header_font
        cc_hdr.fill = header_fill
        cc_hdr.alignment = Alignment(horizontal="center")
    r += 1

    input_col = 9
    local_row = r
    li = {}
    for j, field in enumerate(FIELD_ORDER_BEP):
        val = case.get(field, "" if field == "fcbasis" else None)
        cell = pbep.cell(row=local_row, column=input_col + j, value=val)
        li[field] = f"${get_column_letter(input_col + j)}${local_row}"
    result_col_start = input_col + len(FIELD_ORDER_BEP)
    for col_idx in range(input_col, result_col_start + 10):
        pbep.column_dimensions[get_column_letter(col_idx)].hidden = True

    refs_local = {
        "p": li["actual_price"], "incvat": li["includes_vat"], "v": li["vat_rate"],
        "direct": li["direct"], "varfixed": li["varfixed"], "ratenet": li["ratenet"],
        "rategross": li["rategross"], "fc": li["fc"], "fcbasis": li["fcbasis"], "fcs": li["fcs"],
        "fbc": li["fbc"], "cc": li["cc"],
    }
    cell_map_local = {
        "contribution_margin_per_unit": (local_row, result_col_start),
        "fixed_operating_cost": (local_row, result_col_start + 1),
        "break_even_quantity_exact": (local_row, result_col_start + 2),
        "analysis_period_basis": (local_row, result_col_start + 3),
        "_n": (local_row, result_col_start + 4),
        "_g": (local_row, result_col_start + 5),
        "_diagnostic_code": (local_row, result_col_start + 6),
    }
    excel_cell_for = build_bep_formulas(pbep, cell_map_local, refs_local)

    metric_keys_with_basis = METRIC_KEYS_BEP + ["analysis_period_basis"]
    for mk in metric_keys_with_basis:
        label(pbep, r, 2, METRIC_LABELS_BEP.get(mk, "Analysis Period Basis"))
        excel_ref = excel_cell_for[mk]
        fmt = '#,##0.00' if mk in METRIC_KEYS_BEP else "General"
        formula_cell(pbep, r, 3, f"={excel_ref}", fmt=fmt, bold=False)

        py_val = case["python_result"][mk]
        pcv = pbep.cell(row=r, column=4, value=py_val)
        pcv.border = box
        pcv.alignment = Alignment(horizontal="right")
        if isinstance(py_val, (int, float)):
            pcv.number_format = fmt

        py_cell = pcv.coordinate
        diff_f = f'=IF(ISNUMBER({py_cell}),IF(ISNUMBER({excel_ref}),ABS({excel_ref}-{py_cell}),"N/A"),"N/A")'
        formula_cell(pbep, r, 5, diff_f, fmt='0.0000', bold=False)

        pass_f = (
            f'=IFERROR(IF(ISNUMBER({py_cell}),'
            f'IF(ISNUMBER({excel_ref}),IF(ABS({excel_ref}-{py_cell})<={TOL_AMOUNT_BEP},"PASS","FAIL"),"FAIL"),'
            f'IF(NOT(ISNUMBER({excel_ref})),IF({excel_ref}={py_cell},"PASS","FAIL"),"FAIL")),"FAIL")'
        )
        pcell = formula_cell(pbep, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells_bep.append(pcell.coordinate)
        pbep.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
        pbep.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
        r += 1

    # module status tier parity
    label(pbep, r, 2, "Module Status Tier")
    excel_status_f = (
        f'=IF(OR({excel_cell_for["contribution_margin_per_unit"]}="ERROR",{excel_cell_for["fixed_operating_cost"]}="ERROR",{excel_cell_for["break_even_quantity_exact"]}="ERROR"),"ERROR",'
        f'IF(OR({excel_cell_for["contribution_margin_per_unit"]}="UNKNOWN",{excel_cell_for["fixed_operating_cost"]}="UNKNOWN",{excel_cell_for["break_even_quantity_exact"]}="UNKNOWN"),"INCOMPLETE","OK"))'
    )
    excel_status_cell = formula_cell(pbep, r, 3, excel_status_f, fmt="General", bold=False)
    py_status_cell = pbep.cell(row=r, column=4, value=case["python_status"])
    py_status_cell.border = box
    py_status_cell.alignment = Alignment(horizontal="right")
    status_pass_f = f'=IF({excel_status_cell.coordinate}={py_status_cell.coordinate},"PASS","FAIL")'
    status_pcell = formula_cell(pbep, r, 6, status_pass_f, fmt="General", bold=True)
    overall_pass_cells_bep.append(status_pcell.coordinate)
    pbep.conditional_formatting.add(status_pcell.coordinate, FormulaRule(formula=[f'{status_pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
    pbep.conditional_formatting.add(status_pcell.coordinate, FormulaRule(formula=[f'{status_pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
    r += 1

    # primary warning-code diagnostic parity
    label(pbep, r, 2, "Primary Warning Code (diagnostic)")
    diag_cell = excel_cell_for["_diagnostic_code"]
    formula_cell(pbep, r, 3, f"={diag_cell}", fmt="General", bold=False)
    py_code_cell = pbep.cell(row=r, column=4, value=case["python_code"])
    py_code_cell.border = box
    py_code_cell.alignment = Alignment(horizontal="right")
    code_pass_f = f'=IF({diag_cell}={py_code_cell.coordinate},"PASS","FAIL")'
    code_pcell = formula_cell(pbep, r, 6, code_pass_f, fmt="General", bold=True)
    overall_pass_cells_bep.append(code_pcell.coordinate)
    pbep.conditional_formatting.add(code_pcell.coordinate, FormulaRule(formula=[f'{code_pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
    pbep.conditional_formatting.add(code_pcell.coordinate, FormulaRule(formula=[f'{code_pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
    r += 1

    # independent self-check: |Q_BEP * CMu - FC| <= tol, SKIP when Q_BEP not numeric
    label(pbep, r, 2, "Self-Check: |Q_BEP × CMu − FC| ≤ tol")
    q_ref = excel_cell_for["break_even_quantity_exact"]
    cmu_ref = excel_cell_for["contribution_margin_per_unit"]
    fc_ref = excel_cell_for["fixed_operating_cost"]
    selfcheck_f = (
        f'=IF(NOT(ISNUMBER({q_ref})),"SKIP",'
        f'IF(ABS({q_ref}*{cmu_ref}-{fc_ref})<=0.01,"PASS","FAIL"))'
    )
    selfcheck_cell = formula_cell(pbep, r, 3, selfcheck_f, fmt="General", bold=False)
    pbep.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
    selfcheck_cell.alignment = Alignment(horizontal="left")
    self_pass_f = f'=IF({selfcheck_cell.coordinate}="FAIL","FAIL","PASS")'
    self_pcell = formula_cell(pbep, r, 6, self_pass_f, fmt="General", bold=True)
    overall_pass_cells_bep.append(self_pcell.coordinate)
    pbep.conditional_formatting.add(self_pcell.coordinate, FormulaRule(formula=[f'{self_pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
    pbep.conditional_formatting.add(self_pcell.coordinate, FormulaRule(formula=[f'{self_pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
    r += 1
    r += 1

section_row(pbep, r, "Overall (25/26 scenarios live Excel evaluation — TC13 reference-only, no FC currency input in the flat model)", span=2); r += 1
label(pbep, r, 2, "All metrics/status/code/self-check PASS?")
overall_f_bep = f'=IF(COUNTIF({overall_pass_cells_bep[0]}:{overall_pass_cells_bep[-1]},"FAIL")=0,"ALL PASS","SOME FAILED")'
oc_bep = formula_cell(pbep, r, 3, overall_f_bep, fmt="General", bold=True)
pbep.conditional_formatting.add(oc_bep.coordinate, FormulaRule(formula=[f'{oc_bep.coordinate}="SOME FAILED"'], fill=PatternFill("solid", fgColor=RED_BG)))
pbep.conditional_formatting.add(oc_bep.coordinate, FormulaRule(formula=[f'{oc_bep.coordinate}="ALL PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))

pbep.freeze_panes = "B4"
print("09_BEP_PARITY_TEST_OK")

# ================================================================
# SHEET: 10_SCENARIO_COMPARE
# ================================================================
from core.engine.scenario_compare import run_scenario_compare  # noqa: E402

SCENARIO_COLS = [3, 4, 5, 6, 7]  # C, D, E, F, G -- scenarios A-E
SCENARIO_LETTERS = ["A", "B", "C", "D", "E"]

ssc = wb.create_sheet("10_SCENARIO_COMPARE")
ssc.sheet_view.showGridLines = False
ssc.column_dimensions["A"].width = 2
ssc.column_dimensions["B"].width = 38
for col_idx in SCENARIO_COLS:
    ssc.column_dimensions[get_column_letter(col_idx)].width = 15

r = 2
title_row(ssc, r, "10. Scenario Compare — Orchestration over MODE A/B/C/BEP (Interactive)", span=7); r += 2

section_row(ssc, r, "BASE INPUT (단일 컴포넌트 기준, 모든 시나리오가 공유)", span=7); r += 1

ROW_BASE_PRICE = r; label(ssc, r, 2, "Base Actual Price"); input_cell(ssc, r, 3, 1000, fmt='#,##0'); r += 1
ROW_BASE_INCVAT = r; label(ssc, r, 2, "Base Price Includes VAT"); input_cell(ssc, r, 3, False); r += 1
ROW_BASE_VAT = r; label(ssc, r, 2, "Base VAT Rate"); input_cell(ssc, r, 3, 0.10, fmt="0.0%"); r += 1
ROW_BASE_TMP = r; label(ssc, r, 2, "Base Target Market Price"); input_cell(ssc, r, 3, 1000, fmt='#,##0'); r += 1
ROW_BASE_DISC = r; label(ssc, r, 2, "Base Discount Rate"); input_cell(ssc, r, 3, 0, fmt="0.0%"); r += 1
ROW_BASE_DIRECT = r; label(ssc, r, 2, "Base Direct Cost Amount"); input_cell(ssc, r, 3, 400, fmt='#,##0'); r += 1
ROW_BASE_VARFIXED = r; label(ssc, r, 2, "Base Variable Fixed Cost (override 불가)"); input_cell(ssc, r, 3, 100, fmt='#,##0'); r += 1
ROW_BASE_RATENET = r; label(ssc, r, 2, "Base Net-Sales Fee Rate (override 불가)"); input_cell(ssc, r, 3, 0, fmt="0.0%"); r += 1
ROW_BASE_RATEGROSS = r; label(ssc, r, 2, "Base Gross-Payment Fee Rate (override 불가)"); input_cell(ssc, r, 3, 0, fmt="0.0%"); r += 1
ROW_BASE_FC = r; label(ssc, r, 2, "Base Fixed Operating Cost Amount"); input_cell(ssc, r, 3, 50000, fmt='#,##0'); r += 1
ROW_BASE_TCM = r; label(ssc, r, 2, "Base Target Contribution Margin Rate"); input_cell(ssc, r, 3, 0.3, fmt="0.0%"); r += 2

BASE_REFS = {
    "p": f"$C${ROW_BASE_PRICE}", "incvat": f"$C${ROW_BASE_INCVAT}", "v": f"$C${ROW_BASE_VAT}",
    "tmp": f"$C${ROW_BASE_TMP}", "disc": f"$C${ROW_BASE_DISC}", "direct": f"$C${ROW_BASE_DIRECT}",
    "varfixed": f"$C${ROW_BASE_VARFIXED}", "ratenet": f"$C${ROW_BASE_RATENET}",
    "rategross": f"$C${ROW_BASE_RATEGROSS}", "fc": f"$C${ROW_BASE_FC}", "tcm": f"$C${ROW_BASE_TCM}",
}

section_row(ssc, r, "SCENARIO CONTROL", span=7); r += 1
ROW_BASELINE_ID = r
label(ssc, r, 2, "Baseline Scenario ID")
input_cell(ssc, r, 3, "A")
label(ssc, r, 4, "활성 Scenario ID 중 하나와 반드시 일치해야 함 — 첫 번째 시나리오를 자동 baseline으로 취급하지 않음")
r += 1
label(ssc, r, 2, (
    "Excel v0.1: 최대 5개 시나리오(A~E) — Python Core는 이 제한이 없음(2개 이상 임의 개수). "
    "이는 presentation-layer 제한이며 계산 semantics 제한이 아님."
), italic=True, wrap=True)
r += 2

section_row(ssc, r, "SCENARIO IDENTITY (blank Scenario ID = 비활성)", span=7); r += 1
ROW_SCENARIO_ID = r
label(ssc, r, 2, "Scenario ID")
for i, col_idx in enumerate(SCENARIO_COLS):
    input_cell(ssc, r, col_idx, SCENARIO_LETTERS[i])
r += 1
ROW_SCENARIO_LABEL = r
label(ssc, r, 2, "Label")
default_labels = ["Baseline", "Price Up", "Price Down", "", ""]
for i, col_idx in enumerate(SCENARIO_COLS):
    input_cell(ssc, r, col_idx, default_labels[i])
r += 2

section_row(ssc, r, "OVERRIDE INPUT (Mode: inherit / null / value)", span=7); r += 1


_DV_MODE = DataValidation(type="list", formula1='"inherit,null,value"', allow_blank=False)


def _override_field(ws_, r_, label_text, default_mode="inherit", default_values=None):
    if _DV_MODE not in ws_.data_validations.dataValidation:
        ws_.add_data_validation(_DV_MODE)
    row_mode = r_
    label(ws_, row_mode, 2, f"{label_text} — Mode")
    default_values = default_values or [None] * 5
    refs = {}
    for i, col_idx in enumerate(SCENARIO_COLS):
        # a column whose default_values entry is set must default to Mode="value", or the
        # pre-filled example value would be silently ignored (Mode="inherit" never reads it).
        col_default_mode = "value" if default_values[i] is not None else default_mode
        input_cell(ws_, row_mode, col_idx, col_default_mode)
        _DV_MODE.add(ws_.cell(row=row_mode, column=col_idx))
    row_value = row_mode + 1
    label(ws_, row_value, 2, f"{label_text} — Value")
    for i, col_idx in enumerate(SCENARIO_COLS):
        input_cell(ws_, row_value, col_idx, default_values[i], fmt='#,##0.00')
        refs[SCENARIO_LETTERS[i]] = {
            "mode": f"${get_column_letter(col_idx)}${row_mode}",
            "value": f"${get_column_letter(col_idx)}${row_value}",
        }
    return refs, row_mode + 2


OVERRIDE_REFS_SSC = {}
_row = r
_field_defs = [
    ("p", "Actual Price", [None, 1200, 800, None, None]),
    ("incvat", "Price Includes VAT", [None, None, None, None, None]),
    ("tmp", "Target Market Price", [None, None, None, None, None]),
    ("disc", "Discount Rate", [None, None, None, None, None]),
    ("tcm", "Target CM Rate", [None, None, None, None, None]),
    ("v", "VAT Rate", [None, None, None, None, None]),
    ("direct", "Direct Cost Amount", [None, None, 300, None, None]),
    ("fc", "Fixed Operating Cost Amount", [None, None, None, None, None]),
]
for field_key, field_label, defaults in _field_defs:
    refs, _row = _override_field(ssc, _row, field_label, default_values=defaults)
    for letter in SCENARIO_LETTERS:
        OVERRIDE_REFS_SSC.setdefault(letter, {})[field_key] = refs[letter]
r = _row
r += 1

section_row(ssc, r, "RESULT SUMMARY (계산값 — 직접 입력 금지)", span=7); r += 1

ROW_MAP_SSC = {}
_summary_rows = [
    "n", "cmu", "cmr", "mode_a_status",
    "s_b", "l_b", "mode_b_status",
    "adc", "eff_direct", "gap", "mode_c_status",
    "fc_result", "q_bep", "bep_status",
    "scenario_status",
]
_summary_labels = {
    "n": "MODE A: Net Sales ex VAT", "cmu": "MODE A: Contribution Margin", "cmr": "MODE A: CM Rate",
    "mode_a_status": "MODE A: Status",
    "s_b": "MODE B: Required Selling Price", "l_b": "MODE B: Required List Price",
    "mode_b_status": "MODE B: Status",
    "adc": "MODE C: Allowable Direct Cost", "eff_direct": "MODE C: Actual Direct Cost",
    "gap": "MODE C: Direct Cost Gap", "mode_c_status": "MODE C: Status",
    "fc_result": "BEP: Fixed Operating Cost", "q_bep": "BEP: Break-Even Quantity",
    "bep_status": "BEP: Status",
    "scenario_status": "SCENARIO OVERALL STATUS",
}
for key in set(_summary_rows) | {"eff_p", "eff_incvat", "eff_v", "eff_tmp", "eff_disc", "eff_tcm", "eff_fc",
                                   "g", "c_b", "d_b", "n_b", "g_b", "nc", "gc"}:
    ROW_MAP_SSC[key] = None  # placeholder, assigned below only for keys actually placed on-sheet

for key in _summary_rows:
    label(ssc, r, 2, _summary_labels[key])
    ROW_MAP_SSC[key] = r
    r += 1
    if key in ("mode_a_status", "mode_b_status", "mode_c_status", "bep_status"):
        r += 0  # keep contiguous, no extra spacing needed

# hidden helper rows for every intermediate cell build_scenario_compare_column_formulas() needs
# but that isn't part of the visible summary (eff_*, g, MODE B/C intermediates)
_hidden_keys = ["eff_p", "eff_incvat", "eff_v", "eff_tmp", "eff_disc", "eff_tcm", "eff_direct", "eff_fc",
                 "g", "c_b", "d_b", "n_b", "g_b", "nc", "gc"]
for key in _hidden_keys:
    if ROW_MAP_SSC.get(key):
        continue
    ROW_MAP_SSC[key] = r
    r += 1
ssc.row_dimensions.group(ROW_MAP_SSC[_hidden_keys[0]], ROW_MAP_SSC[_hidden_keys[-1]], hidden=True)
r += 1

SCENARIO_RESULTS_SSC = {}
for i, col_idx in enumerate(SCENARIO_COLS):
    letter = SCENARIO_LETTERS[i]
    SCENARIO_RESULTS_SSC[letter] = build_scenario_compare_column_formulas(
        ssc, col_idx, ROW_MAP_SSC, BASE_REFS, OVERRIDE_REFS_SSC[letter],
    )

for key in _summary_rows:
    row = ROW_MAP_SSC[key]
    fmt = "General" if key.endswith("status") else ("0.00%" if key == "cmr" else '#,##0.00')
    for col_idx in SCENARIO_COLS:
        c = ssc.cell(row=row, column=col_idx)
        c.font = value_font
        c.border = box
        c.alignment = Alignment(vertical="center", horizontal="right")
        c.number_format = fmt
        coord = c.coordinate
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="ERROR"'], fill=PatternFill("solid", fgColor=RED_BG)))
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="UNKNOWN"'], fill=PatternFill("solid", fgColor=YELLOW)))
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="NOT_APPLICABLE"'], fill=PatternFill("solid", fgColor=YELLOW)))
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'ISNUMBER({coord})'], fill=PatternFill("solid", fgColor=GREEN_BG)))

r += 1
section_row(ssc, r, "DELTA vs. Baseline (SPEC.md section 13/14)", span=7); r += 1

ROW_BASELINE_COL_INDEX = r
label(ssc, r, 2, "Baseline Column Index (내부 계산용, MATCH)")
id_range = f"$C${ROW_SCENARIO_ID}:$G${ROW_SCENARIO_ID}"
baseline_id_ref = f"$C${ROW_BASELINE_ID}"
baseline_idx_formula = f'=IFERROR(MATCH({baseline_id_ref},{id_range},0),0)'
baseline_idx_cell = ssc.cell(row=r, column=3, value=baseline_idx_formula).coordinate
label(ssc, r, 4, "0이면 baseline_scenario_id를 활성 Scenario ID 중에서 찾지 못한 것 (request-level ERROR)")
r += 1

DELTA_ROWS_SSC = {}
_delta_defs = [("net_sales_ex_vat_delta", "n"), ("contribution_margin_delta", "cmu"),
               ("contribution_margin_rate_delta", "cmr"), ("break_even_quantity_delta", "q_bep")]
for delta_key, source_key in _delta_defs:
    label(ssc, r, 2, delta_key)
    DELTA_ROWS_SSC[delta_key] = r
    source_row = ROW_MAP_SSC[source_key]
    source_range = f"$C${source_row}:$G${source_row}"
    for col_idx in SCENARIO_COLS:
        col_letter = get_column_letter(col_idx)
        own_cell = f"${col_letter}${source_row}"
        baseline_value_formula_part = f'INDEX({source_range},1,{baseline_idx_cell})'
        delta_formula = _delta_precedence_formula(own_cell, baseline_value_formula_part, baseline_idx_cell)
        c = formula_cell(ssc, r, col_idx, delta_formula, fmt='#,##0.00', bold=False)
        coord = c.coordinate
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="ERROR"'], fill=PatternFill("solid", fgColor=RED_BG)))
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="UNKNOWN"'], fill=PatternFill("solid", fgColor=YELLOW)))
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'{coord}="NOT_APPLICABLE"'], fill=PatternFill("solid", fgColor=YELLOW)))
        ssc.conditional_formatting.add(coord, FormulaRule(formula=[f'ISNUMBER({coord})'], fill=PatternFill("solid", fgColor=GREEN_BG)))
    r += 1
r += 1

section_row(ssc, r, "REQUEST-LEVEL STATUS", span=7); r += 1
ROW_ACTIVE_COUNT = r
label(ssc, r, 2, "Active Scenario Count")
active_count_formula = f'=COUNTIF({id_range},"?*")'
ssc.cell(row=r, column=3, value=active_count_formula)
r += 1
ROW_DUP_ID = r
label(ssc, r, 2, "Duplicate Scenario ID Exists?")
dup_formula = f'=SUMPRODUCT((COUNTIF({id_range},{id_range})>1)*({id_range}<>""))>0'
ssc.cell(row=r, column=3, value=f"={dup_formula[1:]}")
r += 1
ROW_REQUEST_STATUS = r
label(ssc, r, 2, "Request-Level Status")
request_status_formula = (
    f'=IF($C${ROW_ACTIVE_COUNT}<2,"ERROR: SCENARIO_COUNT_BELOW_MINIMUM",'
    f'IF($C${ROW_DUP_ID}=TRUE,"ERROR: DUPLICATE_SCENARIO_ID",'
    f'IF(ISBLANK({baseline_id_ref}),"ERROR: MISSING_BASELINE_SCENARIO_ID",'
    f'IF({baseline_idx_cell}=0,"ERROR: BASELINE_SCENARIO_ID_NOT_FOUND","OK"))))'
)
req_status_cell = formula_cell(ssc, r, 3, request_status_formula, fmt="General")
ssc.merge_cells(start_row=r, start_column=3, end_row=r, end_column=7)
req_status_cell.alignment = Alignment(horizontal="left")
ssc.conditional_formatting.add(req_status_cell.coordinate, FormulaRule(formula=[f'LEFT({req_status_cell.coordinate},5)="ERROR"'], fill=PatternFill("solid", fgColor=RED_BG)))
ssc.conditional_formatting.add(req_status_cell.coordinate, FormulaRule(formula=[f'{req_status_cell.coordinate}="OK"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
r += 1

ROW_OVERALL_STATUS_SSC = r
label(ssc, r, 2, "Scenario Compare Overall Status")
active_scenario_status_cells = [f"${get_column_letter(c)}${ROW_MAP_SSC['scenario_status']}" for c in SCENARIO_COLS]
error_check_ssc = "+".join(f'IF({cell}="ERROR",1,0)' for cell in active_scenario_status_cells)
incomplete_check_ssc = "+".join(f'IF({cell}="INCOMPLETE",1,0)' for cell in active_scenario_status_cells)
overall_formula_ssc = (
    f'=IF({req_status_cell.coordinate}<>"OK",{req_status_cell.coordinate},'
    f'IF(({error_check_ssc})>0,"ERROR",IF(({incomplete_check_ssc})>0,"INCOMPLETE","OK")))'
)
overall_cell_ssc = formula_cell(ssc, r, 3, overall_formula_ssc, fmt="General")
ssc.merge_cells(start_row=r, start_column=3, end_row=r, end_column=7)
overall_cell_ssc.alignment = Alignment(horizontal="left")
ssc.conditional_formatting.add(overall_cell_ssc.coordinate, FormulaRule(formula=[f'LEFT({overall_cell_ssc.coordinate},5)="ERROR"'], fill=PatternFill("solid", fgColor=RED_BG)))
ssc.conditional_formatting.add(overall_cell_ssc.coordinate, FormulaRule(formula=[f'{overall_cell_ssc.coordinate}="OK"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
r += 2

label(ssc, r, 2, (
    "Excel-only 표기 한계: Request-Level Status가 OK가 아닐 때도 각 시나리오 컬럼의 개별 계산 셀은 "
    "계속 숫자를 보여줍니다(수식 자체를 동적으로 비활성화할 수 없음) — 이 경우 "
    "Scenario Compare Overall Status가 request-level 오류를 표시하므로 개별 셀 값은 무시해야 합니다. "
    "Python Core는 이 경우 scenarios=[] 를 반환해 계산 자체를 하지 않습니다(진짜 실행 0회)."
), italic=True, wrap=True)

ssc.freeze_panes = "C4"

dv_bool = DataValidation(type="list", formula1='"TRUE,FALSE"', allow_blank=True)
ssc.add_data_validation(dv_bool)
dv_bool.add(ssc.cell(row=ROW_BASE_INCVAT, column=3))
_incvat_value_row = int(OVERRIDE_REFS_SSC["A"]["incvat"]["value"].split("$")[-1])
for col_idx in SCENARIO_COLS:
    dv_bool.add(ssc.cell(row=_incvat_value_row, column=col_idx))
print("10_SCENARIO_COMPARE_OK")

# ================================================================
# SHEET: 11_SCENARIO_COMPARE_PARITY
# ================================================================
from core.engine.scenario_compare import run_scenario_compare  # noqa: E402,F811

pscc = wb.create_sheet("11_SCENARIO_COMPARE_PARITY")
pscc.sheet_view.showGridLines = False
pscc.column_dimensions["A"].width = 2
pscc.column_dimensions["B"].width = 40
for col in "CDEFG":
    pscc.column_dimensions[col].width = 15

r = 2
title_row(pscc, r, "11. Python Engine vs Excel Formula — Scenario Compare Parity Test", span=6); r += 1
pscc.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7)
c = pscc.cell(row=r, column=2, value=(
    "각 케이스는 docs/features/scenario_compare/CASE.md TC1-37 중 Excel에서 표현 가능한 대표 케이스에 "
    "대응하며, core/engine/scenario_compare.py의 run_scenario_compare()를 동일 base_input/overrides로 "
    "실행한 Python 참조값과, 같은 조건을 Excel 수식(build_scenario_compare_column_formulas)으로 독립 "
    "재계산한 값을 비교합니다. 각 케이스는 최소 2개(baseline + 1개 변형) scenario 컬럼을 사용하며, "
    "Scenario ID/Baseline ID/override mode(inherit/null/value)까지 리터럴로 심습니다. 허용오차 0.01."
))
c.font = note_font
c.alignment = Alignment(wrap_text=True, vertical="top")
pscc.row_dimensions[r].height = 56
r += 2

TOL_SC = 0.01
LOCAL_BASE_COL = 9   # column I — this case's literal Base Input values
LOCAL_SCEN_COLS = [10, 11, 12]  # columns J, K, L — up to 3 scenario columns per case
for _c in [LOCAL_BASE_COL] + LOCAL_SCEN_COLS:
    pscc.column_dimensions[get_column_letter(_c)].hidden = True

_OVR_FIELDS = ["p", "incvat", "v", "tmp", "disc", "tcm", "direct", "fc", "rategross"]
_BASE_FIELD_ORDER = ["p", "incvat", "v", "tmp", "disc", "direct", "varfixed", "ratenet", "rategross", "fc", "tcm"]


def _write_local_base(ws_, row0, values):
    refs = {}
    for i, field in enumerate(_BASE_FIELD_ORDER):
        row = row0 + i
        ws_.cell(row=row, column=LOCAL_BASE_COL, value=values.get(field))
        refs[field] = f"${get_column_letter(LOCAL_BASE_COL)}${row}"
    return refs, row0 + len(_BASE_FIELD_ORDER)


def _write_local_overrides(ws_, row0, col, overrides):
    """overrides: dict field -> (mode, value); fields not present default to ("inherit", None)."""
    refs = {}
    row = row0
    for field in _OVR_FIELDS:
        mode, value = overrides.get(field, ("inherit", None))
        ws_.cell(row=row, column=col, value=mode)
        ws_.cell(row=row + 1, column=col, value=value)
        refs[field] = {"mode": f"${get_column_letter(col)}${row}", "value": f"${get_column_letter(col)}${row + 1}"}
        row += 2
    return refs, row


def _write_case_id_row(ws_, row, scenario_ids, baseline_id):
    for i, sid in enumerate(scenario_ids):
        ws_.cell(row=row, column=LOCAL_SCEN_COLS[i], value=sid)
    baseline_cell = f"${get_column_letter(LOCAL_BASE_COL)}${row}"
    ws_.cell(row=row, column=LOCAL_BASE_COL, value=baseline_id)
    return baseline_cell


DEFAULT_BASE_VALUES = {
    "p": 1000, "incvat": False, "v": 0.10, "tmp": 1000, "disc": 0, "direct": 400,
    "varfixed": 100, "ratenet": 0, "rategross": 0, "fc": 50000, "tcm": 0.3,
}


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


_FIELD_TO_OVERRIDE_GROUP = {
    "p": ("components", "actual_price"), "incvat": ("components", "price_includes_vat"),
    "tmp": ("components", "target_market_price"), "disc": ("components", "discount_rate"),
    "tcm": ("targets", "target_contribution_margin_rate"), "v": ("tax", "vat_rate"),
    "direct": ("cost_items", "amount"), "fc": ("cost_items", "amount"), "rategross": ("cost_items", "rate"),
}
_FIELD_TO_ITEM_ID = {"direct": "direct", "fc": "fixed_ops", "rategross": "var_gross_payment"}


def _make_sc_request(base_values, scenario_specs, baseline_id):
    """scenario_specs: list of (scenario_id, overrides_dict) where overrides_dict maps
    field -> (mode, value), mirroring the Excel case's own override rows exactly."""
    scenarios = []
    for sid, overrides in scenario_specs:
        py_overrides = {"components": [], "cost_items": [], "targets": {}, "tax": {}}
        comp_fields, item_fields = {}, {}
        for field, (mode, value) in overrides.items():
            if mode == "inherit":
                continue
            group, subfield = _FIELD_TO_OVERRIDE_GROUP[field]
            py_value = None if mode == "null" else value
            if group == "components":
                comp_fields[subfield] = py_value
            elif group == "targets":
                py_overrides["targets"]["target_contribution_margin_rate"] = py_value
            elif group == "tax":
                py_overrides["tax"]["vat_rate"] = py_value
            elif group == "cost_items":
                item_id = _FIELD_TO_ITEM_ID[field]
                item_fields.setdefault(item_id, {})[subfield] = py_value
        if comp_fields:
            py_overrides["components"].append({"component_id": "main", **comp_fields})
        for item_id, fields in item_fields.items():
            py_overrides["cost_items"].append({"item_id": item_id, **fields})
        if not py_overrides["targets"]:
            del py_overrides["targets"]
        if not py_overrides["tax"]:
            del py_overrides["tax"]
        if not py_overrides["components"]:
            del py_overrides["components"]
        if not py_overrides["cost_items"]:
            del py_overrides["cost_items"]
        scenarios.append({"scenario_id": sid, "label": sid, "overrides": py_overrides})
    return {"base_input": _make_client_input(base_values), "baseline_scenario_id": baseline_id, "scenarios": scenarios}


PARITY_CASES_SC = [
    dict(name="TC1. Baseline current price (no overrides)", scenarios=[("A", {}), ("B", {})], baseline="A"),
    dict(name="TC2. Price increase", scenarios=[("A", {}), ("B", {"p": ("value", 1200)})], baseline="A"),
    dict(name="TC3. Price decrease", scenarios=[("A", {}), ("B", {"p": ("value", 800)})], baseline="A"),
    dict(name="TC4. Direct cost reduction", scenarios=[("A", {}), ("B", {"direct": ("value", 300)})], baseline="A"),
    dict(name="TC5. Gross-payment fee increase", base={**DEFAULT_BASE_VALUES, "v": 0.10},
         scenarios=[("A", {}), ("B", {"rategross": ("value", 0.05)})], baseline="A"),
    dict(name="TC6. Target CM increase", scenarios=[("A", {}), ("B", {"tcm": ("value", 0.5)})], baseline="A"),
    dict(name="TC7. Market price below required price", scenarios=[("A", {}), ("B", {"tmp": ("value", 500)})], baseline="A"),
    dict(name="TC8. Market price above required price", scenarios=[("A", {}), ("B", {"tmp": ("value", 1500)})], baseline="A"),
    dict(name="TC9. Negative allowable cost (reuses MODE C TC11)",
         base={"p": 10000, "incvat": False, "v": 0.10, "tmp": 10000, "disc": 0, "direct": 400,
               "varfixed": 0, "ratenet": 0.3, "rategross": 0.3, "fc": 50000, "tcm": 0.5},
         scenarios=[("A", {}), ("B", {})], baseline="A"),
    dict(name="TC10. BEP improves (price up)", scenarios=[("A", {}), ("B", {"p": ("value", 1300)})], baseline="A"),
    dict(name="TC11. BEP worsens (discount)", scenarios=[("A", {}), ("B", {"p": ("value", 700)})], baseline="A"),
    dict(name="TC12. Fixed operating cost increase", scenarios=[("A", {}), ("B", {"fc": ("value", 80000)})], baseline="A"),
    dict(name="TC13. VAT display comparison (net_sales_ex_vat_delta=0)",
         scenarios=[("A", {}), ("B", {"p": ("value", 1100), "incvat": ("value", True)})], baseline="A"),
    dict(name="TC14. UNKNOWN scenario (VAT-inclusive display, v null)",
         scenarios=[("A", {}), ("B", {"incvat": ("value", True), "v": ("null", None)})], baseline="A"),
    dict(name="TC15. ERROR scenario (negative fixed cost)",
         scenarios=[("A", {}), ("B", {"fc": ("value", -10000)})], baseline="A"),
    dict(name="TC16. BEP NOT_APPLICABLE (CMu=0)", scenarios=[("A", {}), ("B", {"p": ("value", 500)})], baseline="A"),
    dict(name="TC17. Baseline change (recompute deltas)",
         scenarios=[("A", {}), ("B", {"p": ("value", 1200)})], baseline="B"),
    dict(name="TC18. Omitted override inherits base",
         scenarios=[("A", {}), ("B", {"p": ("value", 1200), "incvat": ("inherit", None)})], baseline="A"),
    dict(name="TC19. Explicit null override -> UNKNOWN",
         scenarios=[("A", {}), ("B", {"p": ("null", None)})], baseline="A"),
    dict(name="TC20. Baseline self-delta, numeric OK",
         scenarios=[("A", {}), ("B", {"p": ("value", 1200)})], baseline="A"),
    dict(name="TC21. Baseline self-delta, UNKNOWN",
         scenarios=[("A", {"incvat": ("value", True), "v": ("null", None)}), ("B", {})], baseline="A"),
    dict(name="TC22. Baseline self-delta, NOT_APPLICABLE",
         scenarios=[("A", {"p": ("value", 500)}), ("B", {})], baseline="A"),
    dict(name="TC24. Duplicate scenario_id (request-level ERROR)",
         scenarios=[("A", {}), ("A", {"p": ("value", 1200)})], baseline="A", request_level=True),
    dict(name="TC25. Baseline not found (request-level ERROR)",
         scenarios=[("A", {}), ("B", {"p": ("value", 1200)})], baseline="Z", request_level=True),
    dict(name="TC37. Invalid baseline (STEP-3) -- CASE.md TC37",
         # W's rategross override (1.5) is out of client_input.schema.json's cost_item.rate
         # [0,1] bound, so the real run_scenario_compare() call genuinely fails W at STEP 3 --
         # this is not a simulated/hard-coded Excel-only semantic, the Python reference is the
         # actual STEP-3 rejection. `invalid_scenario_id` additionally drives the Excel-only
         # validity_ref simulation control (parity-sheet only, see
         # build_scenario_compare_column_formulas docstring) on W's column, since Excel formulas
         # cannot themselves evaluate JSON Schema bounds. B/D mirror CASE.md TC37's own two valid
         # siblings (price up to 1200 / direct cost down to 300).
         scenarios=[("W", {"rategross": ("value", 1.5)}), ("B", {"p": ("value", 1200)}),
                    ("D", {"direct": ("value", 300)})],
         baseline="W", invalid_scenario_id="W"),
]


def _run_python_reference(case):
    base_values = case.get("base", DEFAULT_BASE_VALUES)
    req = _make_sc_request(base_values, case["scenarios"], case["baseline"])
    result = run_scenario_compare(req)
    return req, result


overall_pass_cells_sc = []

for case in PARITY_CASES_SC:
    section_row(pscc, r, case["name"], span=5); r += 1
    for i, h in enumerate(["Check", "Excel Result", "Python Reference", "Difference", "PASS / FAIL"]):
        hcell = pscc.cell(row=r, column=2 + i, value=h)
        hcell.font = header_font
        hcell.fill = header_fill
        hcell.alignment = Alignment(horizontal="center")
    r += 1

    base_values = case.get("base", DEFAULT_BASE_VALUES)
    req, py_result = _run_python_reference(case)

    local_row = r
    # _write_local_base only ever touches LOCAL_BASE_COL (column I); the Scenario ID / Baseline
    # ID row below it is written at its OWN row (base_end_row) so it can never collide with the
    # base value block, even though both use column I for their own single value.
    base_refs, base_end_row = _write_local_base(pscc, local_row, base_values)
    scenario_ids = [sid for sid, _ in case["scenarios"]]
    id_row = base_end_row
    baseline_id_cell = _write_case_id_row(pscc, id_row, scenario_ids, case["baseline"])

    override_refs_by_scenario = {}
    ovr_row0 = id_row + 1
    for i, (sid, overrides) in enumerate(case["scenarios"]):
        refs, _ = _write_local_overrides(pscc, ovr_row0, LOCAL_SCEN_COLS[i], overrides)
        override_refs_by_scenario[sid] = refs
    ovr_end_row = ovr_row0 + len(_OVR_FIELDS) * 2

    # Parity-sheet-only validity-simulation row (see build_scenario_compare_column_formulas'
    # `validity_ref` docstring) -- only allocated for the one case that needs it
    # (invalid_scenario_id set), so every other case's row layout is byte-for-byte unchanged.
    # This lives in the same already-hidden LOCAL_SCEN_COLS/LOCAL_BASE_COL block (columns I-L are
    # all `.hidden = True` above), so it is not a new visible input anywhere in the workbook, and
    # it has no counterpart on 10_SCENARIO_COMPARE (the interactive sheet never calls
    # build_scenario_compare_column_formulas with a validity_ref) -- it is not a Scenario Validity
    # UI control and not a schema field.
    validity_row = None
    if case.get("invalid_scenario_id"):
        validity_row = ovr_end_row
        label(pscc, validity_row, LOCAL_BASE_COL - 1,
              "validity (parity test-only, NOT a schema field)", italic=True)
        result_keys_start = ovr_end_row + 1
    else:
        result_keys_start = ovr_end_row

    row_map_case = {}
    result_keys = ["n", "cmu", "cmr", "mode_a_status", "c_b", "d_b", "n_b", "g_b", "s_b", "l_b",
                   "mode_b_status", "g", "nc", "gc", "adc", "gap", "mode_c_status",
                   "fc_result", "q_bep", "bep_status", "scenario_status",
                   "eff_p", "eff_incvat", "eff_v", "eff_tmp", "eff_disc", "eff_tcm", "eff_direct", "eff_fc", "eff_rategross"]
    for j, key in enumerate(result_keys):
        row_map_case[key] = result_keys_start + j
    result_end_row = result_keys_start + len(result_keys)

    excel_results_by_scenario = {}
    for i, (sid, overrides) in enumerate(case["scenarios"]):
        col = LOCAL_SCEN_COLS[i]
        validity_ref = None
        if validity_row is not None and case.get("invalid_scenario_id") == sid:
            validity_ref = pscc.cell(row=validity_row, column=col, value="invalid").coordinate
        excel_results_by_scenario[sid] = build_scenario_compare_column_formulas(
            pscc, col, row_map_case, base_refs, override_refs_by_scenario[sid],
            validity_ref=validity_ref,
        )

    # delta section (only meaningful for the non-request-level cases)
    id_row_range = f"${get_column_letter(LOCAL_SCEN_COLS[0])}${id_row}:${get_column_letter(LOCAL_SCEN_COLS[len(case['scenarios']) - 1])}${id_row}"
    baseline_idx_formula = f'=IFERROR(MATCH({baseline_id_cell},{id_row_range},0),0)'
    baseline_idx_cell = pscc.cell(row=result_end_row, column=LOCAL_BASE_COL, value=baseline_idx_formula).coordinate

    delta_defs = [("net_sales_ex_vat_delta", "n"), ("contribution_margin_delta", "cmu"),
                  ("contribution_margin_rate_delta", "cmr"), ("break_even_quantity_delta", "q_bep")]
    excel_deltas_by_scenario = {sid: {} for sid, _ in case["scenarios"]}
    delta_row0 = result_end_row + 1
    for k, (delta_key, source_key) in enumerate(delta_defs):
        source_row = row_map_case[source_key]
        n_active = len(case["scenarios"])
        source_range = f"${get_column_letter(LOCAL_SCEN_COLS[0])}${source_row}:${get_column_letter(LOCAL_SCEN_COLS[n_active - 1])}${source_row}"
        for i, (sid, _) in enumerate(case["scenarios"]):
            own_cell = f"${get_column_letter(LOCAL_SCEN_COLS[i])}${source_row}"
            baseline_val = f'INDEX({source_range},1,{baseline_idx_cell})'
            delta_formula = _delta_precedence_formula(own_cell, baseline_val, baseline_idx_cell)
            cell = pscc.cell(row=delta_row0 + k, column=LOCAL_SCEN_COLS[i], value=delta_formula).coordinate
            excel_deltas_by_scenario[sid][delta_key] = cell

    # The local block above (columns I-L, rows local_row..delta_row0+len(delta_defs)) can run to
    # many more rows than the comparison block below it (columns B-G) needs -- if `r` were left
    # where the comparison header row left it, the NEXT case's local block would start while this
    # case's own local block is still in use in the same hidden columns, silently overlapping and
    # corrupting both. Advance `r` past whichever the local block actually used before writing any
    # comparison row, and use that same advanced `r` as this case's comparison-row cursor too.
    r = delta_row0 + len(delta_defs) + 1

    # ---- comparison rows ----
    if case.get("request_level"):
        # Live Excel request-level diagnostic — same two checks 10_SCENARIO_COMPARE's own
        # Request-Level Status computes (duplicate Scenario ID via COUNTIF, baseline not found
        # via MATCH), reproduced locally for this case's own 2-column ID range so the check is a
        # genuine independent recomputation, not a copy of the Python status.
        dup_formula = f'=SUMPRODUCT((COUNTIF({id_row_range},{id_row_range})>1)*({id_row_range}<>""))>0'
        dup_cell = pscc.cell(row=r, column=LOCAL_BASE_COL, value=dup_formula).coordinate
        excel_request_status_formula = (
            f'=IF({dup_cell}=TRUE,"ERROR: DUPLICATE_SCENARIO_ID",'
            f'IF({baseline_idx_cell}=0,"ERROR: BASELINE_SCENARIO_ID_NOT_FOUND","OK"))'
        )
        label(pscc, r, 2, "Request-Level Status: Excel (independent recompute)")
        excel_req_cell = formula_cell(pscc, r, 3, excel_request_status_formula, fmt="General", bold=False)
        py_status_label = "ERROR" if py_result["status"] == "ERROR" else "OK"
        py_cell = pscc.cell(row=r, column=4, value=py_status_label)
        py_cell.border = box
        pass_f = (
            f'=IF(AND(LEFT({excel_req_cell.coordinate},5)="ERROR",{py_cell.coordinate}="ERROR"),"PASS",'
            f'IF(AND({excel_req_cell.coordinate}="OK",{py_cell.coordinate}="OK"),"PASS","FAIL"))'
        )
        pcell = formula_cell(pscc, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells_sc.append(pcell.coordinate)
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
        r += 1
        label(pscc, r, 2, "(request-level case: mode engines not evaluated for this comparison — "
                           "only the preflight diagnostic itself is being parity-tested)")
        r += 1
        r += 1
        continue

    py_scenarios_by_id = {s["scenario_id"]: s for s in py_result["scenarios"]}
    for sid, _ in case["scenarios"]:
        py_s = py_scenarios_by_id[sid]
        label(pscc, r, 2, f"Scenario {sid}: scenario_status")
        excel_ref = excel_results_by_scenario[sid]["scenario_status"]
        formula_cell(pscc, r, 3, f"={excel_ref}", fmt="General", bold=False)
        py_val = py_s["scenario_status"]
        pcv = pscc.cell(row=r, column=4, value=py_val)
        pcv.border = box
        pass_f = f'=IF({excel_ref}={pcv.coordinate},"PASS","FAIL")'
        pcell = formula_cell(pscc, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells_sc.append(pcell.coordinate)
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
        r += 1

        # key metric: contribution_margin (cmu) and break_even_quantity_exact (q_bep)
        for metric_key, py_metric_key, fmt in [("cmu", "contribution_margin", '#,##0.00'), ("q_bep", "break_even_quantity_exact", '#,##0.00')]:
            excel_ref = excel_results_by_scenario[sid][metric_key]
            label(pscc, r, 2, f"Scenario {sid}: {py_metric_key}")
            formula_cell(pscc, r, 3, f"={excel_ref}", fmt=fmt, bold=False)
            if "summary" in py_s:
                pc_main = py_s["summary"]["per_component"]["main"]
                mode_a_m = pc_main["mode_a"]["contribution_margin"] if py_metric_key == "contribution_margin" else None
                bep_m = pc_main["bep"]["break_even_quantity_exact"] if py_metric_key == "break_even_quantity_exact" and pc_main["bep"] else None
                metric_obj = mode_a_m or bep_m
                py_val = metric_obj["value"] if metric_obj and metric_obj["status"] == "OK" else (metric_obj["status"] if metric_obj else "N/A")
            else:
                # "summary" absent means this scenario itself failed STEP 3 (SPEC.md section 7) --
                # no absolute result exists at all, matching the Excel-side validity_ref
                # simulation, which forces this scenario's own metric cells to the literal
                # string "ERROR" (never a plain "no data" placeholder).
                py_val = "ERROR"
            pcv = pscc.cell(row=r, column=4, value=py_val)
            pcv.border = box
            if isinstance(py_val, (int, float)):
                pcv.number_format = fmt
            diff_f = f'=IF(ISNUMBER({pcv.coordinate}),IF(ISNUMBER({excel_ref}),ABS({excel_ref}-{pcv.coordinate}),"N/A"),"N/A")'
            formula_cell(pscc, r, 5, diff_f, fmt='0.0000', bold=False)
            pass_f = (
                f'=IFERROR(IF(ISNUMBER({pcv.coordinate}),'
                f'IF(ISNUMBER({excel_ref}),IF(ABS({excel_ref}-{pcv.coordinate})<={TOL_SC},"PASS","FAIL"),"FAIL"),'
                f'IF(NOT(ISNUMBER({excel_ref})),IF({excel_ref}={pcv.coordinate},"PASS","FAIL"),"FAIL")),"FAIL")'
            )
            pcell = formula_cell(pscc, r, 6, pass_f, fmt="General", bold=True)
            overall_pass_cells_sc.append(pcell.coordinate)
            pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
            pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
            r += 1

        # deltas (skip for scenarios without deltas in python, i.e. STEP3-invalid non-baseline)
        if "deltas" in py_s:
            py_deltas = py_s["deltas"]["per_component"]["main"]
            for delta_key, _ in delta_defs:
                excel_ref = excel_deltas_by_scenario[sid][delta_key]
                label(pscc, r, 2, f"Scenario {sid}: {delta_key}")
                formula_cell(pscc, r, 3, f"={excel_ref}", fmt='#,##0.0000', bold=False)
                py_d = py_deltas[delta_key]
                py_val = py_d["value"] if py_d["status"] == "OK" else py_d["status"]
                pcv = pscc.cell(row=r, column=4, value=py_val)
                pcv.border = box
                if isinstance(py_val, (int, float)):
                    pcv.number_format = '#,##0.0000'
                pass_f = (
                    f'=IFERROR(IF(ISNUMBER({pcv.coordinate}),'
                    f'IF(ISNUMBER({excel_ref}),IF(ABS({excel_ref}-{pcv.coordinate})<={TOL_SC},"PASS","FAIL"),"FAIL"),'
                    f'IF(NOT(ISNUMBER({excel_ref})),IF({excel_ref}={pcv.coordinate},"PASS","FAIL"),"FAIL")),"FAIL")'
                )
                pcell = formula_cell(pscc, r, 6, pass_f, fmt="General", bold=True)
                overall_pass_cells_sc.append(pcell.coordinate)
                pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
                pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
                r += 1

    if case.get("invalid_scenario_id"):
        # Only added for the invalid-baseline case (every other case's layout/checks are
        # untouched). "Scenario Compare: overall status" independently recomputes SPEC.md
        # section 9's rollup (ERROR if any scenario_status=ERROR) from this case's own 3
        # scenario_status cells and compares it against the real run_scenario_compare() result's
        # top-level status. The warning-count row is a direct read of the real Python result's
        # warnings[] (not an Excel formula — Excel has no warnings[] representation in this
        # workbook), asserting BASELINE_SCENARIO_INVALID_FOR_DELTA appears exactly once, per
        # SPEC.md section 14a / CASE.md TC37.
        status_cells = [excel_results_by_scenario[sid]["scenario_status"] for sid, _ in case["scenarios"]]
        or_terms = ",".join(f'{c}="ERROR"' for c in status_cells)
        overall_status_formula = f'=IF(OR({or_terms}),"ERROR","OK")'
        label(pscc, r, 2, "Scenario Compare: overall status")
        excel_ref = formula_cell(pscc, r, 3, overall_status_formula, fmt="General", bold=False)
        py_val = py_result["status"]
        pcv = pscc.cell(row=r, column=4, value=py_val)
        pcv.border = box
        pass_f = f'=IF({excel_ref.coordinate}={pcv.coordinate},"PASS","FAIL")'
        pcell = formula_cell(pscc, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells_sc.append(pcell.coordinate)
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
        r += 1

        label(pscc, r, 2, "Python: BASELINE_SCENARIO_INVALID_FOR_DELTA warning count (expect 1)")
        warning_count = sum(1 for w2 in py_result["warnings"] if w2["code"] == "BASELINE_SCENARIO_INVALID_FOR_DELTA")
        py_wcell = pscc.cell(row=r, column=4, value=warning_count)
        py_wcell.border = box
        pass_f = f'=IF({py_wcell.coordinate}=1,"PASS","FAIL")'
        pcell = formula_cell(pscc, r, 6, pass_f, fmt="General", bold=True)
        overall_pass_cells_sc.append(pcell.coordinate)
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="FAIL"'], fill=PatternFill("solid", fgColor=RED_BG)))
        pscc.conditional_formatting.add(pcell.coordinate, FormulaRule(formula=[f'{pcell.coordinate}="PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))
        r += 1
    r += 1

section_row(pscc, r, "Overall (all Scenario Compare parity checks — live Excel evaluation)", span=2); r += 1
label(pscc, r, 2, "All checks PASS?")
overall_f_sc = f'=IF(COUNTIF({overall_pass_cells_sc[0]}:{overall_pass_cells_sc[-1]},"FAIL")=0,"ALL PASS","SOME FAILED")'
oc_sc = formula_cell(pscc, r, 3, overall_f_sc, fmt="General", bold=True)
pscc.conditional_formatting.add(oc_sc.coordinate, FormulaRule(formula=[f'{oc_sc.coordinate}="SOME FAILED"'], fill=PatternFill("solid", fgColor=RED_BG)))
pscc.conditional_formatting.add(oc_sc.coordinate, FormulaRule(formula=[f'{oc_sc.coordinate}="ALL PASS"'], fill=PatternFill("solid", fgColor=GREEN_BG)))

pscc.freeze_panes = "B4"
print("11_SCENARIO_COMPARE_PARITY_OK")

OUT_PATH = ROOT / "tools" / "excel_simulator" / "Pricing_Harness_Excel_Simulator_v0.5.xlsx"
wb.save(OUT_PATH)
print("SAVED:", OUT_PATH)
