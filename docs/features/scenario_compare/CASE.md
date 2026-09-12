# Scenario Compare — CASE (DRAFT v0.1)

Fictional data only (`client_id: sample_co_eta`) — not any real client. No engine code exists
yet for Scenario Compare itself; every number below is either (a) hand-derived from the already-
frozen MODE A/B/C/BEP formulas (same arithmetic discipline as their own CASE.md files), or (b) a
request/scenario-definition-level outcome that doesn't involve mode arithmetic at all (clearly
marked). All cases share one `base_input` unless noted, built to the same pattern already used in
BEP's CASE.md: single component `main`, `v = 0.10` where VAT rate is known.

## Shared base_input (unless a case overrides otherwise)

```
actual_price = 1000, price_includes_vat = false, vat_rate = 0.10
direct_cost = 400, variable_fixed = 100, net_sales_fee_rate = 0, gross_payment_fee_rate = 0
fixed_operating_cost = 50000 (component-scoped, basis: per_month)
target_contribution_margin_rate = 0.3
target_market_price = 1000 (same component, price_includes_vat = false)
```

Baseline economics (MODE A): `N = 1000`, `direct = 400`, `variable = 100` →
`CM = 500`, `CMR = 0.5`. BEP: `CMu = 500`, `FC = 50000` → `Q_BEP = 100`. MODE B at
`t = 0.3`: `D = 1 − 0.3 = 0.7` (no rate fees) → `N_required = 400/0.7 = 571.43`,
`required_selling_price = 571.43` (VAT-exclusive display). MODE C at `target_market_price=1000,
t=0.3`: `ADC = 1000×0.7 − 0 = 700`, `actual_direct_cost = 400` (reusing the direct-cost item) →
`direct_cost_gap = 300`.

---

**TC1 — baseline = current price**
`scenario_id: "A_baseline"`, no overrides. This scenario is **also** `baseline_scenario_id`.
All four modes OK: `mode_a.contribution_margin = 500`, `mode_b.required_selling_price = 571.43`,
`mode_c.allowable_direct_cost = 700`, `bep.break_even_quantity_exact = 100`.
`scenario_status = OK`. Deltas vs itself: since every source metric here is numeric `OK`
(`contribution_margin=500` etc.), all four self-deltas are `0`/`OK` — see TC33 for the general
rule (self-delta follows the source metric's own status, not an unconditional `0`/`OK` — SPEC.md
§14).

**TC2 — price increase**
`scenario_id: "B_price_up"`, override `product.price_components[main].actual_price = 1200`.
`N=1200` → MODE A: `CM = 1200−400−100 = 700`, `CMR = 0.583`. BEP: `CMu=700, FC=50000` →
`Q_BEP = 71.43`. `scenario_status = OK`.
Deltas vs TC1: `net_sales_ex_vat_delta = +200`, `contribution_margin_delta = +200`,
`contribution_margin_rate_delta ≈ +0.083`, `break_even_quantity_delta ≈ −28.57` (BEP *improves* —
fewer units needed, matches TC10's intent).

**TC3 — price decrease**
`scenario_id: "C_price_down"`, override `actual_price = 800`.
MODE A: `CM = 800−400−100 = 300`, `CMR = 0.375`. BEP: `CMu=300, FC=50000` → `Q_BEP = 166.67`.
`scenario_status = OK`. Deltas vs TC1: `net_sales_ex_vat_delta = −200`, `contribution_margin_delta = −200`,
`break_even_quantity_delta ≈ +66.67` (BEP *worsens* — matches TC11's intent).

**TC4 — direct cost reduction**
`scenario_id: "D_cost_down"`, override `costs.items[direct].amount = 300` (was 400).
MODE A: `CM = 1000−300−100 = 600`, `CMR=0.6`. BEP: `CMu=600` → `Q_BEP = 83.33`. MODE C:
`actual_direct_cost = 300` (the same item, now lower) → `direct_cost_gap = 700−300 = 400` (larger
gap — more room under the allowable ceiling). `scenario_status = OK`.
Deltas vs TC1: `contribution_margin_delta = +100`, `break_even_quantity_delta ≈ −16.67`.

**TC5 — variable fee increase**
`scenario_id: "E_fee_up"`, override `costs.items[var_gross_payment].rate = 0.05` (was 0,
`applies_to_component: main`, `basis: rate_of_gross_payment`). `v=0.10` known so `G = 1100`.
MODE A: `variable_cost_total = 100 + 0.05×1100 = 155`, `CM = 1000−400−155 = 445`. BEP:
`CMu=445` → `Q_BEP = 112.36`. `scenario_status = OK`. Deltas vs TC1:
`contribution_margin_delta = −55`, `break_even_quantity_delta ≈ +12.36`.

**TC6 — target CM increase (MODE B only)**
`scenario_id: "F_target_cm_up"`, override `targets.target_contribution_margin_rate = 0.5`.
MODE A/BEP unaffected (they don't read this field) — `contribution_margin_delta = 0`,
`break_even_quantity_delta = 0` vs TC1. MODE B: `D = 1−0.5 = 0.5` →
`required_selling_price = 400/0.5 = 800`. MODE C: `ADC = 1000×0.5 = 500` (lower ceiling) →
`direct_cost_gap = 500−400 = 100` (down from TC1's 300). `scenario_status = OK`. This case
demonstrates that a delta can legitimately be `0` for some metrics and nonzero for others within
the same scenario — Scenario Compare does not treat a `0` delta as "nothing changed," only as
"this particular metric didn't change."

**TC7 — market price below required price**
`scenario_id: "G_market_below_required"`, override `target_market_price = 500` (MODE B's own
`required_selling_price` at baseline `t=0.3` is `571.43` — TC1). MODE C at `t=0.3`:
`ADC = 500×0.7 = 350`, `actual_direct_cost = 400` → `direct_cost_gap = 350−400 = −50` (negative —
current actual cost exceeds what this lower market price can afford at the target margin).
`mode_c.status = OK` (a negative gap is a valid, computed diagnostic, not an ERROR — matches MODE
C's own `NEGATIVE_ALLOWABLE_COST`-adjacent reasoning for `allowable_direct_cost` itself, though
here it is `direct_cost_gap`, not `allowable_direct_cost`, that goes negative; `allowable_direct_
cost = 350` stays a plain positive OK number in this particular case). `scenario_status = OK`.
This scenario exists specifically to show MODE B's `required_selling_price` (571.43) and MODE C's
market-price input (500) as two independently-sourced numbers that a decision-maker compares
side by side — Scenario Compare does not reconcile or flag the gap between them itself, beyond
showing both in the summary view (SPEC.md §10).

**TC8 — market price above required price**
`scenario_id: "H_market_above_required"`, override `target_market_price = 800` (above MODE B's
571.43). MODE C: `ADC = 800×0.7 = 560`, `actual_direct_cost=400` → `direct_cost_gap = 160`
(comfortable headroom). `scenario_status = OK`. Contrasts directly with TC7 — same summary shape,
opposite economic conclusion, purely from one overridden input.

**TC9 — negative allowable cost scenario**
`scenario_id: "I_negative_adc"`. Rather than deriving new numbers, this scenario directly reuses
**MODE C CASE.md TC11's exact inputs** as its override set
(`target_market_price=10000, target_contribution_margin_rate=0.5, net_sales_fee_rate=0.3,
gross_payment_fee_rate=0.3, vat_rate=0.10, F=0`) → `allowable_direct_cost = −1300`,
`mode_c.status = OK` with the existing non-blocking `NEGATIVE_ALLOWABLE_COST` warning (unchanged
MODE C behavior — Scenario Compare does not alter it). `scenario_status = OK` — a negative,
OK-with-warning `allowable_direct_cost` does not make the scenario ERROR (SPEC.md §9 correctly
does not special-case this, since `mode_c.status` itself stays `OK` per MODE C's own rule).

**TC10 — BEP improves after price increase**
Same as TC2 — included here under its own name to explicitly pin the "BEP improves" framing:
`break_even_quantity_delta` is **negative** (fewer units needed) when price rises with cost
structure held fixed. Cross-referenced from TC2 rather than duplicated with new numbers.

**TC11 — BEP worsens after discount**
`scenario_id: "K_bep_worsens_discount"`, override `actual_price = 700` (a discounted price,
`price_includes_vat` unchanged) — deeper cut than TC3. MODE A: `CM = 700−400−100 = 200`. BEP:
`CMu=200` → `Q_BEP = 250`. `scenario_status = OK`. Deltas vs TC1:
`contribution_margin_delta = −300`, `break_even_quantity_delta = +150` (BEP clearly worsens).

**TC12 — fixed operating cost increase**
`scenario_id: "L_fc_up"`, override `costs.items[fixed_ops].amount = 80000` (was 50000). MODE A/
MODE B/MODE C unaffected (none of them read `fixed_operating_cost`) —
`contribution_margin_delta = 0`. BEP: `FC=80000, CMu=500` → `Q_BEP = 160`. `scenario_status = OK`.
`break_even_quantity_delta = +60`. Demonstrates a delta isolated to exactly one mode (BEP), the
others reporting an unchanged (zero-delta) result — expected, not a bug (dependency isolation
carried up from the mode level).

**TC13 — VAT included vs. excluded display comparison**
Two scenarios: `scenario_id: "M1_vat_excl"` (baseline's own VAT-exclusive display, `actual_price=
1000, price_includes_vat=false`) and `scenario_id: "M2_vat_incl"` (override
`actual_price=1100, price_includes_vat=true` — same underlying `N=1000` economics, VAT-inclusive
display). Both scenarios yield **identical** `mode_a.contribution_margin=500`,
`bep.break_even_quantity_exact=100` — `M1_vat_excl` vs `M2_vat_incl` deltas (if `M1` is baseline)
are all `0`. This case exists to confirm Scenario Compare's pass-through correctly shows that
display convention doesn't change economics (the same principle MODE A/B/C's own CASE.md files
already established — Scenario Compare adds no new claim here, just surfaces the existing one
across two named scenarios for a side-by-side view).

**TC14 — one scenario has UNKNOWN input**
`scenario_id: "N_unknown_vat"`, overrides `product.price_components[main].price_includes_vat =
true`, `tax.vat_rate = null` (now VAT-inclusive display with an unknown rate — MODE A's `N` needs
`v` in this configuration and cannot resolve it). `mode_a.status = INCOMPLETE`
(`actual_price_ex_vat` UNKNOWN, `contribution_margin` UNKNOWN). MODE B/MODE C: `N`-derivations
that also need `v` for this display convention likewise go UNKNOWN/INCOMPLETE where applicable;
BEP's `contribution_margin_per_unit` UNKNOWN → `break_even_quantity_exact` UNKNOWN.
`scenario_status = INCOMPLETE` (no ERROR present, at least one UNKNOWN — SPEC.md §9). All four
delta metrics vs TC1 are `UNKNOWN` (their own inputs are UNKNOWN — SPEC.md §14's propagation
rule).

**TC15 — one scenario has ERROR**
`scenario_id: "O_error_negative_fc"`, override `costs.items[fixed_ops].amount = -10000` (BEP's
own `INVALID_NEGATIVE_COST` rule, unchanged). `bep.status = ERROR`. MODE A/B/C unaffected (still
`OK`, since none of them read `fixed_operating_cost`). `scenario_status = ERROR` (SPEC.md §9 — any
module ERROR makes the whole scenario ERROR, even though 3 of 4 modules are fine) — this
deliberately shows the rollup is strict: a single ERROR module, even alongside three OK modules,
is enough.

**TC16 — NOT_APPLICABLE BEP in one scenario**
`scenario_id: "P_bep_not_applicable"`, override `actual_price = 500` (so `CM = 500−400−100 = 0`
exactly). `mode_a.contribution_margin = 0`, `status = OK` (a confirmed, valid zero). BEP:
`contribution_margin_per_unit = 0` → `break_even_quantity_exact = {value: null, status:
NOT_APPLICABLE}` with warning `BREAK_EVEN_UNDEFINED_ZERO_MARGIN` (unchanged BEP rule). `bep.status
= OK` (NOT_APPLICABLE doesn't lower module status — `dependency_rules.md` §7). **`scenario_status
= OK`** — this is the case that specifically pins SPEC.md §9's claim that NOT_APPLICABLE never
drags scenario status down, exercised end-to-end through the orchestration layer, not just at the
BEP module level. `break_even_quantity_delta` vs TC1 is itself `NOT_APPLICABLE` (one side of the
delta is NOT_APPLICABLE — SPEC.md §14).

**TC17 — shared variable cost unresolved**
`scenario_id: "Q_shared_variable_unresolved"`, override target: **not expressible via the v0.1
override allowlist** (SPEC.md §3 excludes changing `applies_to_component`/`allocation_rule`) — so
this scenario is instead built with a different `base_input` variant (not an override of the
shared base) that has a `variable_selling_delivery` item with `applies_to_component: "shared"`,
`allocation_rule: "by_component_revenue"`. `mode_a.variable_cost_total` UNKNOWN
(`UNSUPPORTED_SHARED_COST_ALLOCATION`, unchanged canonical rule) → `contribution_margin` UNKNOWN.
BEP's `contribution_margin_per_unit` UNKNOWN likewise (same `economics.sum_cost_category`
dependency). `mode_a.status = INCOMPLETE`, `bep.status = INCOMPLETE`. `scenario_status =
INCOMPLETE`. This case is also a live illustration of SPEC.md §3's exclusion: had the user tried
to express "make this scenario's variable cost shared-unresolved" via an override on the shared
base, the request would have to be rejected as targeting a disallowed field — the correct way to
get this scenario is a different `base_input`, not an override.

**TC18 — shared fixed cost unresolved**
`scenario_id: "R_shared_fixed_unresolved"`, same base-variant approach as TC17: a `base_input`
whose `fixed_operating_cost` item is `applies_to_component: "shared"`,
`allocation_rule: "blended_only"`. `bep.fixed_operating_cost` UNKNOWN
(`FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED`, BEP's deliberate deviation, unchanged) →
`break_even_quantity_exact` UNKNOWN. MODE A/B/C unaffected (`fixed_operating_cost` isn't their
concern). `bep.status = INCOMPLETE`, others `OK`. `scenario_status = INCOMPLETE`.

**TC19 — multi-component scenario → BEP ERROR only**
`scenario_id: "S_multi_component"`, a `base_input` variant with two `price_components[]` entries
(`main`, `addon`). MODE A/B/C each compute whatever they can per-component (unchanged
per-component behavior — MODE A/B/C have no single-component restriction). BEP:
`status = ERROR`, `per_component = {}`, warning `MULTI_COMPONENT_BEP_NOT_SUPPORTED` (unchanged
gate, `dependency_rules.md` §7). `scenario_status = ERROR` (BEP's ERROR alone is enough, per
SPEC.md §9, even though MODE A/B/C are fine) — Scenario Compare does not collapse the two
components into one to "make BEP work," and does not hide BEP's ERROR from the scenario's overall
status just because it stems from a known, documented limitation rather than bad data.

**TC20 — baseline scenario change affects delta reference**
Not a new scenario — a re-run of the TC1-TC3 comparison set with `baseline_scenario_id` changed
from `"A_baseline"` to `"C_price_down"`. Every delta recomputes against TC3's numbers instead of
TC1's: e.g. TC2's (`B_price_up`) `net_sales_ex_vat_delta` becomes `1200−800=+400` (was `+200` against TC1),
`contribution_margin_delta` becomes `700−300=+400` (was `+200`). This case exists specifically to
confirm deltas are **never cached against a fixed reference** — changing `baseline_scenario_id`
and re-deriving the summary/delta view must reproduce this recomputation, not reuse stale numbers
from a prior baseline choice.

**TC21 — duplicate `scenario_id`**
Request with two scenarios both named `"A_baseline"`. Per SPEC.md §15: **the entire Scenario
Compare request is rejected** — no partial result, no "last one wins." Expected outcome: a
request-level error, not a per-scenario ERROR entry.

**TC22 — missing `baseline_scenario_id`**
Request omits `baseline_scenario_id` entirely. Per SPEC.md §13/§15: rejected — no fallback to
"the first scenario in the list."

**TC23 — `baseline_scenario_id` not found**
Request sets `baseline_scenario_id = "Z_does_not_exist"`, no scenario in the list has that id.
Per SPEC.md §15: rejected.

**TC24 — scenario count = 1**
Request contains exactly one scenario. Per SPEC.md §16's lower bound: rejected — "comparing" one
scenario to itself is not a comparison. Expected outcome: request-level error, same tier as
TC21-23.

**TC25 — scenario count = 5**
Request contains five scenarios (e.g. TC1-TC3, TC6, TC12) with a valid `baseline_scenario_id`.
Per SPEC.md §16: accepted — 5 is within both the Python core's unbounded capacity and the
anticipated (not-yet-built) Excel v0.1 display ceiling. Expected outcome: normal successful
comparison, each scenario's own status per its own inputs (mix of OK results per the numbers
already derived above), no request-level rejection.

**TC26 — duplicate `component_id` in `base_input`**
`base_input.product.price_components[]` has two entries both with `component_id: "main"`. Per
SPEC.md §3/§7 STEP 1: **request rejected** before any scenario is built — this is a `base_input`-
level defect (every scenario would inherit the same ambiguity, since every scenario is a deep
copy of the same `base_input`), not a per-scenario one.

**TC27 — duplicate `item_id` in `base_input`**
`base_input.costs.items[]` has two entries both with `item_id: "direct"`. Per SPEC.md §3/§7
STEP 1: **request rejected**, same reasoning as TC26.

**TC28 — override references an unknown `component_id`**
A scenario's `overrides.components[]` names `component_id: "addon"`, but `base_input` has only
`"main"`. Per SPEC.md §5/§7/§15 (finalized): **the whole request is rejected** at STEP 1 — not a
scenario-level ERROR, and never silently ignored or silently treated as adding a new component.

**TC29 — override references an unknown `item_id`**
A scenario's `overrides.cost_items[]` names `item_id: "shipping"`, but `base_input.costs.items[]`
has no such `item_id`. Per SPEC.md §5/§7/§15: **request rejected** at STEP 1, same reasoning as
TC28.

**TC30 — duplicate override target within one scenario**
A single scenario's `overrides.components[]` contains two entries both with
`component_id: "main"` (e.g. one setting `actual_price`, another setting `discount_rate` — even
though the two entries don't touch the same *field*, they target the same *object*). Per SPEC.md
§5/§7 STEP 1: **request rejected** — not resolved by merging the two entries' fields together,
and not resolved by "last one wins." A scenario needing to change both `actual_price` and
`discount_rate` on the same component must express both fields on **one** `components[]` entry
for that `component_id`.

**TC31 — omitted field inherits base value**
A scenario's `overrides.components[]` entry for `"main"` sets only `actual_price = 1200` and
omits `price_includes_vat`/`discount_rate`. Per SPEC.md §5: the merged scenario's
`price_includes_vat`/`discount_rate` are exactly `base_input`'s own values (`false`/whatever
`base_input` had), untouched — not reset to `null`, not defaulted to any other value. This is the
same scenario as TC2, restated to pin the omission behavior specifically (TC2 itself already
relies on this but doesn't call it out as its own point).

**TC32 — explicit `null` override**
A scenario's `overrides.components[]` entry for `"main"` sets `actual_price: null` explicitly
(present in the override, valued `null` — not omitted). Per SPEC.md §5: the merged scenario's
`actual_price` becomes `null`, meaning UNKNOWN exactly as a hand-authored Client Input with a
blank `actual_price` would. `mode_a.actual_price_ex_vat` → UNKNOWN, `mode_a.contribution_margin`
→ UNKNOWN, `bep.contribution_margin_per_unit` → UNKNOWN, `bep.break_even_quantity_exact` →
UNKNOWN. `mode_c` is unaffected (its own price source, `target_market_price`, wasn't touched).
`scenario_status = INCOMPLETE` (no ERROR, at least one UNKNOWN). Contrast directly with TC31: an
*omitted* field keeps the base value; an *explicit null* field becomes UNKNOWN — the two are not
the same, and this case exists specifically to prove the distinction is actually implemented, not
just stated in prose.

**TC33 — baseline self-delta when its source metrics are numeric OK**
`baseline_scenario_id = "A_baseline"` (TC1's own numbers — `contribution_margin=500`,
`break_even_quantity_exact=100`, both `OK`). `A_baseline`'s own delta row reports
`net_sales_ex_vat_delta = 0`, `contribution_margin_delta = 0`, `contribution_margin_rate_delta =
0`, `break_even_quantity_delta = 0`, all `status: OK` — computed by the **same status-propagation
rule** as every other scenario's delta (SPEC.md §14: both operands numeric `OK` → subtract, `OK`),
not a special "self-comparison" case. This is `0` **because the source metric happens to be
numeric `OK`**, not because it is being compared against itself — TC35/TC36 show the same
self-comparison producing a non-`0`/non-`OK` result when the source metric isn't numeric `OK`.

**TC35 — baseline self-delta when its source metric is UNKNOWN**
`scenario_id: "U_baseline_unknown"` used as `baseline_scenario_id`, built like TC14 (override
`price_includes_vat=true, tax.vat_rate=null` → `mode_a.contribution_margin` UNKNOWN,
`bep.break_even_quantity_exact` UNKNOWN). Per SPEC.md §14 (revised): `U_baseline_unknown`'s own
`contribution_margin_delta` = `{value: null, status: "UNKNOWN"}`, **not** `0`/`OK` — `UNKNOWN −
UNKNOWN` is still UNKNOWN, self-comparison does not manufacture a known value. Any sibling
scenario compared against this baseline would show the same UNKNOWN-status deltas for these two
metrics, propagated from the baseline side regardless of the sibling's own status (§14's `ERROR >
UNKNOWN > NOT_APPLICABLE > OK` rule — UNKNOWN on either side is enough).

**TC36 — baseline self-delta when its source metric is NOT_APPLICABLE**
`scenario_id: "V_baseline_not_applicable"` used as `baseline_scenario_id`, built like TC16
(`actual_price=500` → `contribution_margin=0` → `bep.break_even_quantity_exact` NOT_APPLICABLE).
Per SPEC.md §14 (revised): `V_baseline_not_applicable`'s own `break_even_quantity_delta` =
`{value: null, status: "NOT_APPLICABLE"}` — comparing "no meaningful break-even quantity" against
itself does not become a meaningful `0`. (Its `contribution_margin_delta` is still `0`/`OK` in
this specific case, since `contribution_margin` itself is a numeric `0`, `OK` — only
`break_even_quantity_exact`, the metric that actually went NOT_APPLICABLE, is affected. This
contrast is the point of the case: NOT_APPLICABLE on one metric does not infect a sibling metric's
own, independently-numeric delta.)

**TC37 — baseline scenario itself fails STEP 3**
`baseline_scenario_id = "W_baseline_invalid"`; that scenario's override sets
`costs.items[direct].rate = 1.5` (out of `cost_item.rate`'s `[0,1]` schema bound — passes STEP 1's
identifier checks since `item_id: "direct"` genuinely exists in `base_input`, but the merged
document fails STEP 3's schema validation). Two sibling scenarios (`"B_price_up"`/TC2's
overrides, `"D_cost_down"`/TC4's overrides) are also in the request. Per SPEC.md §14a: `
W_baseline_invalid.scenario_status = ERROR`, no `mode_a`/`mode_b`/`mode_c`/`bep` results for it.
`B_price_up` and `D_cost_down` still run their own STEP 2-6 fully and report their own absolute
results normally (`contribution_margin=700`/`600` respectively, unaffected by the baseline's
failure). Both siblings' delta rows show all four delta metrics as `{value: null, status:
"ERROR"}`, with a `BASELINE_SCENARIO_INVALID_FOR_DELTA` warning at the `scenario_compare_result`
level naming `"W_baseline_invalid"` and its STEP-3 error. `scenario_compare_result.status = ERROR`
overall (at least one scenario — the baseline itself — is ERROR), but the comparison is not
aborted: both siblings' absolute numbers are fully present and correct in the result, only their
delta rows are ERROR.

**TC34 — VAT-inclusive/exclusive scenarios compared via `net_sales_ex_vat_delta`**
Extends TC13: with `"M1_vat_excl"` as baseline, `"M2_vat_incl"`'s delta row reports
`net_sales_ex_vat_delta = 0` (both resolve to `mode_a.actual_price_ex_vat = 1000`) despite their
raw `actual_price` fields (`1000` vs `1100`) differing — this is the concrete demonstration of
SPEC.md §14's revision rationale: had the delta been computed on raw `actual_price` instead,
`M2_vat_incl` would have shown a spurious `+100` "price increase" that isn't real (the same
underlying market price, displayed two different ways). `net_sales_ex_vat_delta = 0` is the
correct, meaningful answer.

---

## Summary table

| TC | Scenario | Key metric | Scenario status |
|---|---|---|---|
| 1 | baseline | CM=500, Q_BEP=100 | OK |
| 2 | price +200 | CM=700, Q_BEP=71.43 | OK |
| 3 | price −200 | CM=300, Q_BEP=166.67 | OK |
| 4 | direct cost −100 | CM=600, gap=400 | OK |
| 5 | +5% gross-payment fee | CM=445, Q_BEP=112.36 | OK |
| 6 | target CM 0.3→0.5 | required_price=800, gap=100 | OK |
| 7 | market price below required | gap=−50 | OK |
| 8 | market price above required | gap=160 | OK |
| 9 | negative ADC (MODE C TC11 reuse) | ADC=−1300 | OK (+warning) |
| 10 | BEP improves (=TC2) | Q_BEP delta −28.57 | OK |
| 11 | BEP worsens (discount) | CM=200, Q_BEP=250 | OK |
| 12 | FC +30000 | Q_BEP=160, others delta=0 | OK |
| 13 | VAT display comparison | identical economics both ways | OK |
| 14 | UNKNOWN input | all 4 modules affected | INCOMPLETE |
| 15 | ERROR (negative FC) | bep ERROR, others OK | ERROR |
| 16 | NOT_APPLICABLE BEP | CM=0, Q_BEP=NOT_APPLICABLE | OK |
| 17 | shared variable unresolved | mode_a/bep UNKNOWN | INCOMPLETE |
| 18 | shared fixed unresolved | bep UNKNOWN only | INCOMPLETE |
| 19 | multi-component | bep ERROR only | ERROR |
| 20 | baseline change | deltas recompute | OK (deltas change) |
| 21 | duplicate scenario_id | — | request rejected |
| 22 | missing baseline_scenario_id | — | request rejected |
| 23 | baseline_scenario_id not found | — | request rejected |
| 24 | scenario count = 1 | — | request rejected |
| 25 | scenario count = 5 | mixed | request accepted |
| 26 | duplicate component_id in base | — | request rejected |
| 27 | duplicate item_id in base | — | request rejected |
| 28 | override references unknown component_id | — | request rejected |
| 29 | override references unknown item_id | — | request rejected |
| 30 | duplicate override target in one scenario | — | request rejected |
| 31 | omitted field inherits base | actual_price=1200, others unchanged | OK |
| 32 | explicit null override | actual_price=null → all price-derived metrics UNKNOWN | INCOMPLETE |
| 33 | baseline self-delta, source numeric OK | all deltas = 0 | OK |
| 34 | VAT display comparison via net_sales_ex_vat_delta | delta=0 despite differing actual_price | OK |
| 35 | baseline self-delta, source UNKNOWN | contribution_margin_delta = UNKNOWN | UNKNOWN (baseline) |
| 36 | baseline self-delta, source NOT_APPLICABLE | break_even_quantity_delta = NOT_APPLICABLE | OK (baseline) |
| 37 | baseline fails STEP 3 | siblings' absolute results preserved, deltas = ERROR | ERROR (overall) |
