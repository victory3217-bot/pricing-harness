# MODE A — Current Price Diagnosis — CASE

Fictional Sample Company data only (`client_id: sample_co_alpha`) — **not** based on any real
client. Safe for GitHub and workshop use. Source files:

- Input: [`core/schemas/examples/valid/01_simple_one_time_product.json`](../../../core/schemas/examples/valid/01_simple_one_time_product.json)
- Output: [`core/schemas/examples/analysis_results/01_simple_one_time_product.analysis_result.json`](../../../core/schemas/examples/analysis_results/01_simple_one_time_product.analysis_result.json)
  (regenerate with `python core/engine/generate_analysis_results.py`)

## Case 1 — everything known

**Sample Co. Alpha** sells a "프리미엄 텀블러" (premium tumbler) at **35,000 KRW**, VAT-inclusive,
in a 10% VAT market. Costs on file: material 12,000, packaging 1,500 (both direct); PG fee 2.5%
of the gross payment, shipping 3,000 (both variable-selling).

| Step | Calculation | Result |
|---|---|---|
| VAT-exclusive revenue | 35,000 ÷ 1.10 | **31,818.18** |
| Direct cost total | 12,000 + 1,500 | **13,500** |
| **Gross Profit** | 31,818.18 − 13,500 | **18,318.18** (57.6%) |
| PG fee | 35,000 × 2.5% | 875 |
| Variable cost total | 875 + 3,000 | **3,875** |
| **Contribution Margin** | 18,318.18 − 3,875 | **14,443.18** (45.4%) |

Every metric comes back `status: "OK"` — no warnings. This is the clean case: all 7 dependencies
resolved, so the engine trusts every number it prints.

Notice PG fee used the **gross payment** (35,000, the actual amount charged) as its base, not
the VAT-exclusive revenue — that distinction matters and is covered in `SPEC.md`'s rate-basis
table.

## Case 2 — same product, nothing confirmed yet

Take the identical product, but before any cost or tax data has been entered
(`04_incomplete_inputs.json`: `price_includes_vat`, `vat_rate`, every cost `amount`/`rate`, even
`fx.rate_base_per_reporting` — all `null`).

Result: `mode_a.status = "INCOMPLETE"`, all 7 metrics `UNKNOWN`, 7 warnings — one per metric,
each naming exactly which Client Input field is missing. No number is printed as if it were
real. `direct_cost_total` and `variable_cost_total` fail independently (different missing
fields); `gross_profit` fails as a **consequence** of `actual_price_ex_vat` and
`direct_cost_total` both being unresolved (`DOWNSTREAM_UNKNOWN`), and everything after that
fails as a consequence in turn.

This is the direct, concrete fix for what this project's own prior (pre-Harness) prototype
spreadsheet got wrong: it treated the same kind of missing costs as `0` and reported a
plausible-looking 81.5% margin that had no basis in confirmed data. Case 2 is what the same
situation looks like when the engine is honest about what it doesn't know.

## Case 3 — partial data, partial trust

A third, shorter scenario worth knowing about (not a separate example file — see
`tests/test_mode_a.py::test_5_missing_rate_makes_contribution_margin_unknown_but_not_gross_profit`):
if direct costs are known but the PG fee rate is not, `gross_profit` still comes back `OK` (it
never depended on the PG fee) while `contribution_margin` comes back `UNKNOWN`. MODE A doesn't
collapse everything to "insufficient data" the moment *any* field is missing — it resolves
exactly as much as the confirmed data actually supports, per metric.

## Hybrid (HW + SaaS) shape

`03_hybrid_hw_saas.json` (also fictional — a "스마트팩토리 진동 센서" product, unrelated to Case
001) shows two components computed independently: `gross_profit` resolves `OK` for both
`hardware` and `saas_subscription`, but `contribution_margin` comes back `UNKNOWN` for both —
not because any Client Input field is missing, but because their shared variable costs (PG fee,
channel fee, maintenance visits) use `allocation_rule: by_component_revenue` /
`fixed_share`, which requires the not-yet-built `blended` module to split across components.
The warning code and `dependency_paths` (`blended.allocation[...]`) make that distinction
explicit rather than silently guessing a split.
