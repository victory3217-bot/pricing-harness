# BEP (Break-Even Point) — SPEC (DRAFT v0.1)

## 0. Status

Design-only. No Python code, schema change, test, or Excel work exists yet. This document is
the formula/dependency source of truth for BEP once implementation starts — mirrors the role
`docs/features/mode_a_current_price/SPEC.md` etc. play for MODE A/B/C.

## 1. Core question

**"현재 가격과 Contribution Margin 구조에서 고정운영비를 회수하려면 몇 단위를 판매해야
하는가?"** — at the component's *current actual price* (MODE A's price basis, not a target or
market price), how many units must be sold to recover `fixed_operating_cost` for the period that
cost covers?

BEP v0.1 answers this for **the current price only**. It does not accept MODE B's
`required_selling_price` or MODE C's `target_market_price` as an alternate price source — that
substitution (`BEP(required_price)`, `BEP(market_price)`) is explicitly deferred to a future
**Scenario Compare** module, which can run BEP against any of the three modes' price outputs
without BEP itself needing to know which mode produced the number. Keeping BEP's own scope to
"current price" keeps its dependency graph identical in shape to MODE A's (same price source,
same VAT handling, same component boundary).

## 2. Relationship to MODE A/B/C

| Mode | Question | Price source |
|---|---|---|
| MODE A | 지금 이 가격에서 실제로 얼마가 남는가? | `actual_price` (current) |
| MODE B | 목표 마진을 달성하려면 얼마에 팔아야 하는가? | solved for (`required_selling_price`) |
| MODE C | 시장가격·목표마진에서 원가를 얼마까지 쓸 수 있는가? | `target_market_price` (exogenous) |
| **BEP** | **지금 이 가격·마진 구조에서 손익분기 판매량은?** | `actual_price` (current, same as MODE A) |

BEP is the only one of the four that introduces a **quantity** dimension and a **time-period**
dimension — MODE A/B/C are all single-transaction (per-unit) calculations with no notion of "how
many" or "over what period." This is the central new complexity BEP adds (see section 6).

## 3. Contribution Margin source — two candidate designs; **decision: Design 2, independent
   recompute, via a shared `core/engine/economics.py` primitive (IMPLEMENTED)**

BEP does **not** redefine Contribution Margin. Per-unit CM must mean exactly what MODE A's
`contribution_margin` metric means:

```
CM per unit = net_sales_ex_vat − product_service_direct_cost − variable_selling_delivery costs
```

`fixed_operating_cost` is excluded from CM (unchanged from MODE A) — BEP instead consumes it
directly as its numerator (section 5).

Two ways to obtain this CM per unit were compared (full trade-off table in METHOD.md §2):

- **Design 1 — consume `analysis_result.mode_a`**: BEP reads the already-computed MODE A output
  block for the same `client_input`/component.
- **Design 2 — independent recompute**: BEP calls the same per-component cost-aggregation logic
  MODE A uses directly from `client_input`, without depending on a MODE A result object existing.

**Decision for v0.1: Design 2 — implemented.** BEP takes `client_input` as its only input,
exactly like MODE A/B/C do, and computes its own `contribution_margin_per_unit` metric using
MODE A's *semantics* (same cost-category/basis/shared-cost rules), never MODE A's *output
object*. Rationale in METHOD.md §2; summary: this keeps BEP composable with MODE B/C price
substitution in the future Scenario Compare module (section 1) without threading a MODE A result
through every call site, and keeps each mode's `run_*(client_input)` signature uniform.

**Canonical architecture (as built):**

```
MODE A ─┐
        ├→ core/engine/economics.py  (price_converted, sum_cost_category, DIRECT, VARIABLE)
BEP   ──┘
```

MODE A and BEP are siblings that both call `core/engine/economics.py` — **neither imports the
other**, and BEP has no dependency, direct or indirect, on `core/engine/modes/mode_a.py`.
`economics.py` holds exactly the two primitives MODE A and BEP genuinely share (price-basis
conversion glue, and the generic direct/variable-cost-category summation loop) — see section 12
for the explicit boundary of what stays there versus what stays BEP-local. Neither primitive
embeds a module-specific `metric_path` or warning code/message; each caller (MODE A's
`compute_component`, BEP's `compute_component`) builds its own warnings from the plain
`(value, status, dependency_paths)` data the primitive returns — this is why the earlier
contamination-audit concern (a `mode_a.*` path leaking into a BEP warning) was never actually
possible even before this extraction, and remains impossible now that it is architecturally
enforced (BEP literally cannot reach `mode_a.py`'s namespace to build such a path). MODE A itself
was migrated onto `economics.py` at the same time — there are not two implementations of
direct/variable cost aggregation or price-basis conversion in the codebase, one.

## 4. Fixed Operating Cost — current schema reality (checked, not assumed)

`cost_item.cost_category = "fixed_operating_cost"` (`core/schemas/client_input.schema.json`)
carries: `amount`, `rate` (always null in practice — see below), `currency`, `basis`,
`applies_to_component`, `allocation_rule` (only meaningful when `applies_to_component=="shared"`),
and an optional `frequency_per_year`. No `rate`-based fixed cost is meaningful in practice (a
"rate of X" cost is definitionally variable), so `rate` is expected null for this category, same
as `product_service_direct_cost`.

`basis` enum includes `per_month` and `per_unit_per_month` (time-based) alongside `per_unit` /
`per_order` (transaction-based, used by direct/variable costs) and `per_visit` (needs
`frequency_per_year` to annualize). **All four existing example Client Inputs
(`01`–`04` in `core/schemas/examples/valid/`) use `fixed_operating_cost` items with
`basis: "per_month"` and `applies_to_component: "shared"`, `allocation_rule: "blended_only"`** —
this is the de facto real-world pattern the engine will actually see, and it is significant for
section 6's multi-component/shared discussion.

**Critical finding — no analysis-period field exists anywhere in the schema.** There is no
top-level `"period"`, `"analysis_period_months"`, or similar field on `client_input`. The only
period-shaped information is:
- each fixed-cost item's own `basis` (e.g. `per_month` says *this specific cost* is monthly),
- `product.price_components[].type` (`one_time` / `recurring_monthly` / `recurring_annual` /
  `usage_based`), which describes the **revenue** side's time shape, not the cost side's.

Nothing in the schema guarantees these two independently-stated time shapes agree, and nothing
lets BEP *ask* "what period is this whole analysis in" — it can only *infer* a period from
whichever `fixed_operating_cost` items happen to be present. **This is an explicit, unresolved
design gap (see section 14 / METHOD.md §3) — v0.1 does not assume "monthly."** Instead:

- BEP v0.1 requires every `fixed_operating_cost` item contributing to `FC` (section 5) to share
  **the same `basis`** (whatever it is). If they don't, `fixed_operating_cost` is **ERROR**, code
  `INCONSISTENT_FIXED_COST_BASIS` (not silently summed, not silently picking one).
  `per_visit` items require `frequency_per_year` to be annualized before comparison; if it is
  missing on a `per_visit` item, that item alone is UNKNOWN (`MISSING_DEPENDENCY`,
  `costs.items[<id>].frequency_per_year`).
- **`break_even_quantity_exact.unit` is NOT a basis/period string — it is a quantity unit
  (REVISED)**: the earlier draft of this section said the metric's `unit` field should hold the
  literal basis string (e.g. `"per_month"`). **That conflated two genuinely different concepts
  and is rejected.** `fixed_operating_cost`'s `basis` (e.g. `per_month`) states the **analysis
  period** the FC amount is already denominated in — it is *context*, not the thing being
  measured. `break_even_quantity_exact` itself measures a **count of units sold** (a pure number
  — `unit: "units"` or equivalent, not a time string) *within* that period. Concretely: `FC =
  3,000,000 KRW/month`, `CMu = 30,000 KRW/unit` → `Q_BEP = 100` — the canonical reading is **"100
  units, within the same analysis period the fixed cost figure was denominated in (in this
  example, one month)"**, not "100 per-month" as if "per month" were the quantity's own unit.
  `break_even_quantity_exact.unit` must therefore be set to a literal quantity-unit label (e.g.
  `"units"`), never to the FC `basis` string — that basis instead belongs on a **separate,
  explicit context field** (proposed: `analysis_period_basis`, carrying the same literal basis
  string this section previously tried to overload `unit` with), so a consumer can render "100
  units per month" as two distinct facts (quantity, and the period that quantity is implicitly
  scoped to) rather than one conflated string. Whether that context field lives inside the
  `break_even_quantity_exact` metric object itself (e.g. an extra key alongside
  `value`/`status`/`unit`) or as a sibling field on the `bep` per-component block is an
  implementation-time schema-design decision, not fixed here — but the **semantic separation
  itself** (quantity vs. period-context) is fixed as of this revision and must not be
  re-conflated.
- **`fixed_operating_cost` basis = analysis-period context, not a schema field yet (SPEC.md
  contract for v0.1).** The schema has no dedicated `analysis_period` metadata field (section 4's
  original finding stands, confirmed again here). v0.1 does not add one. Instead, this SPEC
  establishes the semantic contract by convention: *whatever single `basis` the contributing
  `fixed_operating_cost` items agree on (checked via `INCONSISTENT_FIXED_COST_BASIS`, unchanged)
  IS the analysis period `break_even_quantity_exact` is implicitly scoped to* — this is a
  documentation-level contract, not a schema-enforced one, and is listed as a future schema-
  metadata expansion candidate (section 18) rather than solved now.
- Whether the *revenue* side (`price_components[].type`) needs to independently agree with the
  FC `basis` (e.g. a `recurring_annual` component paired with `per_month` FC) remains an open
  item (section 18) — v0.1 does not validate this cross-consistency; it is a known gap, not a
  silent bug, and must be called out to any consultant reading the output.

**Negative `fixed_operating_cost.amount` — decision (new rule, scoped to BEP only).** A
contributing item with `amount < 0` is **ERROR**, code `INVALID_NEGATIVE_COST`, dependency
`costs.items[<item_id>].amount` — checked per item, before summing. The Harness does not model
subsidy/refund/negative-cost economics anywhere today (no existing mode reads
`fixed_operating_cost` at all, so this question has never been decided before); rather than
silently allowing a negative fixed cost to reduce `FC` (which would produce a numerically
"valid" but economically nonsensical smaller/negative break-even quantity), BEP treats it as an
invalid input outright. `amount = 0` remains a fully valid explicit zero (section 7) — this rule
targets strictly negative values only. This is a genuinely new validation, not a reuse of an
existing A/B/C rule (none of them ever needed to look at `fixed_operating_cost.amount`'s sign);
flagged here explicitly rather than folded silently into the existing UNKNOWN/ERROR taxonomy.

## 5. Formula

Symbols:

```
N   = net_sales_ex_vat (per unit, current actual price — same as MODE A's actual_price_ex_vat)
CMu = contribution_margin_per_unit (MODE A semantics, section 3)
FC  = fixed_operating_cost for the component/period being analyzed (section 4/6)

Q_BEP = FC / CMu
```

Dependency/status priority is decided **before** the division is attempted (section 6/7), not
inferred post-hoc from a raw Python `ZeroDivisionError` — same discipline as MODE B's
denominator and MODE C's ADC.

## 6. CMu sign semantics (CMu > 0 / = 0 / < 0) — decision (REVISED)

> **Revision note**: the first draft of this section used `break_even_quantity_exact =
> {value: null, status: "OK"}` for CMu ≤ 0. **That is rejected.** `analysis_result.schema.json`
> already defines `metric_status` as `["OK", "UNKNOWN", "ESTIMATED", "NOT_APPLICABLE", "ERROR"]`
> (checked, unchanged) — `NOT_APPLICABLE` exists exactly for "every input is known, but this
> metric has no meaning for this shape," which is a more precise fit than an `OK` metric whose
> value happens to be `null`. `OK` should mean "this is a normal, present number," never "this is
> OK but deliberately empty."

Per dependency_rules.md's canonical status model, a metric that cannot be computed is either
UNKNOWN (missing data) or ERROR (a computable-but-invalid/undefined result). CMu ≤ 0 is neither
of those — it is a **fully valid, fully computed economic diagnosis** (the inputs are all known)
that simply makes "break-even quantity" an undefined concept in the everyday sense (no finite
positive quantity recovers fixed cost, or, at CMu<0, more sales strictly worsen the loss). It is
also not a plain `OK` result, because there is no meaningful number to report. `NOT_APPLICABLE`
is exactly this third case: inputs fully known, metric has no meaningful value for this input
shape.

**Decision:**
- `contribution_margin_per_unit` itself is always a normal OK/UNKNOWN/ERROR metric (its own
  status follows MODE A's existing per-unit CM dependency rules exactly — no new rule here). It
  is never itself `NOT_APPLICABLE` — a computed CMu (even zero/negative) is always a real,
  meaningful number for MODE A's own purposes.
- When `contribution_margin_per_unit` is OK and `> 0`, and `FC` is OK: `break_even_quantity_exact`
  is **OK**, a finite number (`FC / CMu`, which is `0` when `FC = 0` — see section 9's matrix).
- When `contribution_margin_per_unit` is OK and `== 0`: `break_even_quantity_exact` is
  **`{value: null, status: "NOT_APPLICABLE"}`**, with a non-blocking warning code
  `BREAK_EVEN_UNDEFINED_ZERO_MARGIN` — "현재 단위 마진이 0이라 어떤 판매량으로도 고정비를 회수할
  수 없습니다." (When `FC` is also `0`, see section 9's `BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST`
  variant instead.)
- When `contribution_margin_per_unit` is OK and `< 0`: `break_even_quantity_exact` is
  **`{value: null, status: "NOT_APPLICABLE"}`**, with a non-blocking warning code
  `BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN` — "판매할수록 손실이 커지는 구조입니다(단위 마진 음수).
  이 가격·비용구조에서는 손익분기 판매량이라는 개념 자체가 성립하지 않습니다." This holds
  **regardless of `FC`'s value**, including `FC = 0` — raw division (`0 / negative = 0`) is
  mathematically well-defined but must **not** be reported, because the underlying economic claim
  ("this many units breaks even") is false for any CMu<0 regardless of FC; the engine must
  override the raw arithmetic result with `NOT_APPLICABLE` here, not compute-then-report it.
- `break_even_quantity_exact` never outputs `0` for a CMu≤0 case, and never outputs a negative
  number under any circumstance. `NOT_APPLICABLE` with an explanatory warning is the only
  representation of "no break-even quantity exists."

This keeps the canonical 3-tier module-status rule (`dependency_rules.md` §5) unchanged — see
section 15's confirmation that `common.aggregate_module_status()` already treats
`NOT_APPLICABLE` as neither `ERROR` nor `UNKNOWN`, so it never drags module status down. No
`common.py` change is required for this (checked, not modified — section 15).

## 7. Fixed Cost = 0 vs. no item vs. null — decision

Same `null != 0` principle as every other mode (`dependency_rules.md` §1, MODE C CASE.md
TC17/TC18/TC19 precedent):

- **No `fixed_operating_cost` item at all** for the analyzed component (none matches, directly or
  via a resolvable `shared`) → `FC = 0`, confirmed, **OK**. `CMu > 0` and `FC = 0` →
  `Q_BEP = 0` (a genuinely correct, non-null answer: with no fixed cost, the business is
  break-even from the first unit sold).
- **An item exists, `amount = null`** (not yet entered) → that item's contribution is UNKNOWN
  (`MISSING_DEPENDENCY`, `costs.items[<id>].amount`) → `FC` is UNKNOWN → `break_even_quantity_exact`
  UNKNOWN, `DOWNSTREAM_UNKNOWN`.
- **An item exists, `amount = 0`** (explicit) → confirmed 0 contribution from that item, OK — no
  different from "no item," just entered explicitly.

## 8. Quantity rounding — decision (REVISED)

> **Revision note**: the first draft added `break_even_quantity_units = CEILING(exact)` and used
> `price_components[].type` (`one_time` vs `recurring_*`/`usage_based`) as a proxy for whether
> the quantity is discrete. **That proxy is rejected.** `type` describes the component's
> *pricing/revenue timing model*, not quantity discreteness — a `one_time` product can still sell
> in continuous units (bulk material by weight/volume), and a `recurring_monthly` component's
   "quantity" (subscriber count, seat count) is very often exactly integer. The schema has no
> field that actually states whether a component's sales unit is discrete or continuous.
> Inferring that from `type` would be exactly the kind of "임의로 type에서 수량 의미를 추론"
> the review flagged.

**Decision: `break_even_quantity_units` is excluded entirely from v0.1.** Only
`break_even_quantity_exact` (the raw, unrounded `FC / CMu`) is a v0.1 metric. Re-add a rounded
"units" metric only once/if the schema gains an explicit quantity-discreteness field (e.g. a
future `price_components[].unit_type: "discrete" | "continuous"` or similar) — until then, any
rounding decision belongs to the report/dashboard presentation layer (which may reasonably choose
to display `CEILING(exact)` for a specific client context it understands better than the engine
does), not to the BEP engine itself.

## 9. Revenue-at-BEP metrics — decision, and the FC=0 × CMu-sign matrix

**Revenue-at-BEP metrics excluded from v0.1 core metrics.** `break_even_net_sales` /
`break_even_gross_payment` are trivially derivable (`Q_BEP × N` / `Q_BEP × G` respectively) by
any consumer that already has `break_even_quantity_exact` and MODE A's per-unit N/G — adding them
as first-class BEP output metrics duplicates data already available in `analysis_result.mode_a`,
and doubles the VAT-basis
disambiguation surface (which of {ex-VAT, incl-VAT} each figure represents) for no new
information. If a future Dashboard genuinely needs a pre-computed "매출 손익분기점" card, it is a
presentation-layer computation over two existing metrics, not a new BEP engine metric — revisit
only if a concrete Dashboard/consulting requirement asks for it.

**FC=0 × CMu-sign matrix (new, closes a gap in the original draft).** Section 6 and section 7
each covered one axis in isolation; both together determine `break_even_quantity_exact`:

| FC | CMu | `break_even_quantity_exact` | Warning code |
|---|---|---|---|
| `> 0` | `> 0` | OK, `FC / CMu` (finite, positive) | — |
| `= 0` | `> 0` | **OK, `0`** | — (genuinely break-even from unit 1; not a warning case) |
| `> 0` | `= 0` | `NOT_APPLICABLE` | `BREAK_EVEN_UNDEFINED_ZERO_MARGIN` |
| `= 0` | `= 0` | `NOT_APPLICABLE` | `BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST` (new, distinct — both terms of `FC/CMu` are simultaneously zero, a `0/0` indeterminate form, not the same diagnostic as "margin is zero but there's real fixed cost to recover") |
| `> 0` | `< 0` | `NOT_APPLICABLE` | `BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN` |
| `= 0` | `< 0` | `NOT_APPLICABLE` | `BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN` (same code as the `FC>0` row — raw arithmetic `0/negative = 0` is explicitly overridden per section 6's last bullet; `0` is never reported here) |

`0` is a valid `break_even_quantity_exact` value in exactly one row of this table (`FC=0, CMu>0`)
— every other zero/negative-adjacent combination is `NOT_APPLICABLE`, never a raw `0`.

## 10. Actual sales / margin of safety — decision

**Out of v0.1 scope.** `client_input.schema.json` has no field for actual historical/planned sales
quantity anywhere in the schema (checked: no `actual_quantity`, `units_sold`, `sales_volume`, or
equivalent exists). `margin_of_safety` and `required_quantity_gap` both require such a quantity
input to exist first. Adding them now would mean either inventing a new schema field (out of this
phase's scope per section 18) or leaving the metric permanently UNKNOWN — neither is useful.
Revisit once/if a quantity-input field is added to the schema for an unrelated reason (e.g. a
future Validation/Feedback module per `MASTER_NOTE_MAPPING.md` §MN08).

## 11. Multi-component / hybrid — decision (behavior finalized)

**BEP v0.1 = single-component only (Option A), confirmed as a `module_status = ERROR` result —
not a Python exception, and not UNKNOWN.** If `product.price_components[]` has more than one
entry, `run_bep(client_input)` still returns the same `{status, per_component, warnings}` shape
every other mode returns (never raises), but with:

- `status = "ERROR"`,
- `per_component = {}` — no component's metrics are computed at all, not even partially (no
  per-component `FC`/`CMu`/`Q_BEP` leak through),
- one warning: `{code: "MULTI_COMPONENT_BEP_NOT_SUPPORTED", severity: "blocking",
  metric_path: "bep", dependency_paths: ["product.price_components"], message: "BEP v0.1은 단일
  컴포넌트 상품만 지원합니다 — 이 Client Input은 컴포넌트가 2개 이상이라 계산하지 않습니다
  (shared fixed cost 이중계상 방지)."}`.

This is deliberately **ERROR, not UNKNOWN**: a multi-component product is not "missing data" that
could resolve itself once a field is filled in — it is a structurally unsupported shape for this
module version. UNKNOWN would incorrectly suggest a consultant could fix this by entering more
data; ERROR correctly says "this input shape itself is out of v0.1's supported range." BEP v0.1
never computes partial component-level `FC`/`BEP` for a subset of components in this situation,
and never falls back to a blended sales-mix calculation — both explicitly excluded regardless of
how "easy" a particular multi-component input might look (see CASE.md TC18, which shows the gate
applies even when every fixed cost happens to be cleanly component-scoped).

**Evaluation priority — fixed (this is a strict, ordered gate, not a status computed alongside
everything else):**

```
STEP 1 — component-count gate (runs first, unconditionally, before touching anything else):
  len(product.price_components) > 1
    -> status = "ERROR", code = MULTI_COMPONENT_BEP_NOT_SUPPORTED, per_component = {}
    -> STOP. Nothing further is evaluated.

STEP 2 — only reached when exactly one component exists:
  fixed-cost basis consistency (INCONSISTENT_FIXED_COST_BASIS, section 4)
  contribution_margin_per_unit dependency chain (section 3)
  currency (section 13)
  shared-cost allocation classification (section 12)
  negative fixed-cost amount (section 4)
  ... and only then, the FC×CMu division (sections 6/9)
```

**Consequence: if a Client Input is simultaneously multi-component AND has an inconsistent fixed-
cost `basis` across items, the canonical v0.1 result is `MULTI_COMPONENT_BEP_NOT_SUPPORTED` alone
— `INCONSISTENT_FIXED_COST_BASIS` is never evaluated, never appears in `warnings`, and is not
computed "in the background" for informational purposes.** STEP 2's checks are meaningless without
a single, well-defined component to run them against, so there is no partial/parallel evaluation
to report — this is a hard early return, not a priority ranking between two warnings that were
both computed. This mirrors how MODE A/B/C's own dependency evaluation always resolves a metric's
own upstream status before considering that metric's own additional validity checks, generalized
here to a whole-module gate instead of a single metric.

Rationale (matches section 4's finding): all four current example Client Inputs put
`fixed_operating_cost` on `applies_to_component: "shared"` + `allocation_rule: "blended_only"` —
meaning **real fixed-cost data, as currently modeled, is already declared "only meaningful in a
future whole-contract blended view," never as a clean per-component split.** For a
single-component product this is moot (shared-across-one-component is unambiguously "all of it"
in economic effect, even though the schema field's own stated policy says "don't interpret this
per-component" — see section 12's resolution of that specific tension). For a genuine
multi-component (hybrid) product, naively computing `FC_i / CM_i` per component using the full,
un-split `FC` would double/triple-count the same shared fixed cost across every component — the
exact bug the user flagged. Option B (component-specific FC only, shared FC → UNKNOWN per
component) was considered but rejected for v0.1 because, given section 4's finding that *no*
current example has any *component-scoped* (non-shared) `fixed_operating_cost` item at all, Option
B would make BEP permanently UNKNOWN for every existing multi-component example — no better than
declaring it unsupported outright, but with more code and a false appearance of partial support.
Option C (blended sales-mix BEP) is explicitly out of scope per the user's own instruction.
**Revisit Option B once a real multi-component Client Input with component-scoped fixed costs
exists**, or once the blended/shared allocation engine (still `NOT_IMPLEMENTED` everywhere) is
built, whichever comes first.

## 12. Shared allocation canonical rule — BEP-specific refinement (important deviation, justified)

BEP reuses the canonical shared-cost classification (`dependency_rules.md` §4) with **one explicit,
justified deviation** for the `blended_only` branch:

| `applies_to_component` | `allocation_rule` | A/B/C's existing rule | **BEP's rule** |
|---|---|---|---|
| matches the single analyzed component | — | counted directly | counted directly (unchanged) |
| `"shared"` | `"direct"` | ERROR, `INVALID_ALLOCATION_CONFIGURATION` | **unchanged — ERROR** |
| `"shared"` | `"by_component_revenue"` / `"fixed_share"` / missing/unrecognized | UNKNOWN, `UNSUPPORTED_SHARED_COST_ALLOCATION` | **unchanged — UNKNOWN** |
| `"shared"` | `"blended_only"` | **excluded — contributes 0, no warning** (because A/B/C never read `fixed_operating_cost` in the first place, so "excluded" is a no-op for them) | **UNKNOWN**, new code `FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED`, dependency `blended.allocation[<item_id>]` — because BEP's numerator *is* `fixed_operating_cost`, silently treating a real, non-zero fixed cost as excluded/0 would silently understate `FC` and produce a falsely-optimistic `Q_BEP` |

This is the single most important semantic decision this SPEC makes relative to precedent: A/B/C's
"`blended_only` → excluded, no warning" rule was only ever safe *because* those three modes
structurally never consume `fixed_operating_cost` at all (it is filtered out by
`cost_category` before shared-classification is even relevant to them) — "excluded" there means
"this cost category doesn't participate in this metric anyway." BEP is the first mode whose core
numerator *is* that cost category, so the same "excluded" behavior would silently zero out real
data instead of correctly no-op'ing on irrelevant data. Reusing the literal old rule without this
refinement would be a bug, not a simplification — flagged explicitly per the "don't invent a new
rule without justification" instruction, with the justification given here.

Given section 4's finding that 100% of current example data uses `blended_only`, this means BEP
will report **UNKNOWN** for every one of today's four example Client Inputs when they have more
than the trivial single-component case — this is the correct, honest answer given the data
actually says "not allocated per-component," not a bug in the design. CASE.md's cases must
therefore construct component-scoped (non-`blended_only`) fixed-cost items to exercise BEP's OK
path at all.

**`core/engine/economics.py` boundary (as built) — this table is exactly why `fixed_operating_cost`
aggregation is NOT part of the shared module.** `economics.py` holds only what MODE A and BEP
genuinely compute identically: price-basis conversion glue (`price_converted`) and the generic
`product_service_direct_cost`/`variable_selling_delivery` summation loop (`sum_cost_category`),
including *that* loop's own (unchanged, A/B/C-identical) shared-cost handling. This section's
`blended_only` deviation applies only to `fixed_operating_cost`, a category `sum_cost_category`
never touches — so `_sum_fixed_operating_cost()` (`core/engine/modes/bep.py`) is a separate,
BEP-local function with its own shared-cost loop, not a variant or extension of
`sum_cost_category()`. This is a deliberate boundary, not an oversight: forcing
`fixed_operating_cost`'s different `blended_only` semantics into the shared function (e.g. via a
category-specific flag) would make `economics.py` carry BEP-specific policy that MODE A doesn't
need and shouldn't have to reason about — narrower, separate functions are the actual minimal
shared surface here, not a generalized single loop parameterized for every category. The same
boundary applies to `analysis_period_basis` tracking, the CM≤0/`NOT_APPLICABLE` sign logic
(section 6/9), and the multi-component hard gate (section 11) — all four stay in `bep.py`,
none of them are shared with or reachable from `mode_a.py`.

## 13. Currency

Unchanged from MODE A/B/C: `FC` and `N`/`CMu` must both land in `fx.reporting_currency` via
`common.convert_to_reporting()` — no new currency rule. Unsupported currency on a contributing
`fixed_operating_cost` item → ERROR (existing `convert_to_reporting` behavior, reused verbatim).

## 14. Output metrics — v0.1 core set (REVISED)

```
contribution_margin_per_unit     (metric, OK/UNKNOWN/ERROR — MODE A CM semantics)
fixed_operating_cost             (metric, OK/UNKNOWN/ERROR — section 4/7/12)
break_even_quantity_exact        (metric, OK/NOT_APPLICABLE(§6/§9)/UNKNOWN/ERROR;
                                   unit = a quantity-unit label (e.g. "units"), NEVER the FC
                                   basis string — §4's REVISED subsection)
```

`analysis_period_basis` (the FC `basis` string `break_even_quantity_exact` is implicitly scoped
to — §4) is context, not itself an output metric; whether it is carried as a field inside the
`break_even_quantity_exact` metric object or as a sibling field on the `bep` per-component block
is left open (§18) — the semantic split (quantity vs. period) is fixed, its schema shape is not.

`break_even_quantity_units` (§8), `break_even_net_sales` / `break_even_gross_payment` (§9), and
`margin_of_safety`-family (§10) are explicitly NOT v0.1 metrics.

Module status: canonical 3-tier via `aggregate_module_status()`, unchanged. §15 confirms
`NOT_APPLICABLE` does not create a 4th tier or otherwise affect module status.

## 15. UNKNOWN / ERROR / "infeasible" — summary, and confirmation of `aggregate_module_status()`

**Confirmed against the actual current `core/engine/common.py` (read, not modified):**

```python
def aggregate_module_status(metrics):
    statuses = [m["status"] for m in metrics]
    if any(s == ERROR for s in statuses):
        return ERROR
    if any(s == UNKNOWN for s in statuses):
        return "INCOMPLETE"
    return OK
```

This function only ever checks for the literal strings `"ERROR"` and `"UNKNOWN"`. A metric whose
status is `"NOT_APPLICABLE"` (or `"OK"` or `"ESTIMATED"`) matches neither check and falls through
to the final `return OK` — exactly the candidate rule this review proposed: **ERROR present →
module ERROR; no ERROR but UNKNOWN present → module INCOMPLETE; only OK/NOT_APPLICABLE present →
module OK.** This is already true today, for free, with **zero changes to `common.py`** —
confirmed by reading the function, not by modifying it. `analysis_result.schema.json`'s
`metric_status` enum already includes `NOT_APPLICABLE` as a first-class value alongside OK/
UNKNOWN/ESTIMATED/ERROR, so no schema change is needed either to represent a
`NOT_APPLICABLE`-status `break_even_quantity_exact` metric.

**UNKNOWN** (`aggregate_module_status` → INCOMPLETE):
- `contribution_margin_per_unit` dependency missing (same causes as MODE A's CM chain: price/VAT
  fields blank, a cost item present with `amount`/`rate` null).
- `fixed_operating_cost` item present with `amount = null`.
- `fixed_operating_cost` item on a `per_visit` basis missing `frequency_per_year`.
- Shared `fixed_operating_cost` item with `by_component_revenue`/`fixed_share`/unrecognized
  `allocation_rule` (canonical rule, unchanged).
- Shared `fixed_operating_cost` item with `allocation_rule = "blended_only"` — **BEP-specific
  deviation, §12**.

**ERROR** (`aggregate_module_status` → ERROR):
- Negative `fixed_operating_cost.amount` on a contributing item — **new rule, §4**, code
  `INVALID_NEGATIVE_COST`.
- Unsupported currency on a contributing item.
- Shared `fixed_operating_cost` item with `allocation_rule = "direct"` (canonical
  `INVALID_ALLOCATION_CONFIGURATION`, unchanged).
- More than one `price_components[]` entry — **finalized, §11**: `module_status = "ERROR"`, code
  `MULTI_COMPONENT_BEP_NOT_SUPPORTED`, `per_component = {}` (nothing partially computed).
- Inconsistent `basis` across contributing `fixed_operating_cost` items (§4,
  `INCONSISTENT_FIXED_COST_BASIS`).

**NOT_APPLICABLE** (does not affect module status, confirmed above) — the "infeasible" case,
**finalized, §6/§9**: `break_even_quantity_exact` is `NOT_APPLICABLE` whenever
`contribution_margin_per_unit` is OK and `≤ 0` (with or without `FC = 0` — the FC×CMu matrix in
§9 covers all four combinations), carrying one of `BREAK_EVEN_UNDEFINED_ZERO_MARGIN` /
`BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST` / `BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN` as a
non-blocking warning. This is neither UNKNOWN (all inputs are known) nor ERROR (nothing is
invalid) nor a plain OK-with-a-number — it is the dedicated fourth status value the schema
already provides for exactly this situation, module status stays OK.

## 16. Master Note boundary

Per `docs/reference/MASTER_NOTE_PRICING_REFERENCE.md` §9 (BEP/Feasibility row) and
`docs/methodology/MASTER_NOTE_MAPPING.md` §9: the Master Note (MN07, primary; MN06, secondary)
supports the *conceptual* framing only — that a business model must move from qualitative to
quantitative, that MN06→MN07 hands over price/cost-margin-structure/revenue-model, and that
feasibility must be checked at a specific price and quantity. **`MASTER_NOTE_MAPPING.md` §9
explicitly states**: "BEP 계산식(고정비÷Contribution Margin 단가 등 구체 공식) — Reference에
표준 공식 없음" — the Master Note does not define `Q_BEP = FC / CMu` or any of this SPEC's
status/dependency/shared-cost rules. This entire document is Pricing Harness Internal
Specification, same boundary already established for MODE B (`dependency_rules.md` intro) and
MODE C. Do not describe any formula or status rule in this document as something the Master Note
"defines" — only as something the Master Note's *problem framing* motivates.

## 17. Scope exclusions (v0.1)

Not in this phase (design or implementation): BEP Python code, schema changes, tests, Excel,
multi-component/hybrid BEP (§11), a real shared-cost allocation engine, blended sales-mix BEP,
Scenario Compare (§1's future price-substitution feature), Dashboard, `margin_of_safety`/actual-
quantity metrics (§10), `break_even_net_sales`/`break_even_gross_payment` (§9), and any commit.

## 18. Remaining open design items (explicit, not silently resolved)

Only genuinely undecided items remain in this list — everything else raised across this design's
review rounds has a fixed decision recorded in the section noted.

1. **Revenue-side `type` vs. FC `basis` cross-validation.** Whether `price_components[].type`
   (revenue-side period, e.g. `recurring_annual`) must be cross-validated against the fixed-cost
   `basis` (cost-side period, e.g. `per_month`) is unresolved (§4). v0.1 does not check this; a
   mismatched pairing produces a numerically "valid" but conceptually mismatched `Q_BEP` with no
   warning. Flagged, not fixed.
2. **Analysis-period schema metadata.** Whether the schema should eventually gain an explicit
   analysis-period field/concept (so `break_even_quantity_exact`'s implicit period-scoping,
   §4's REVISED subsection, becomes schema-enforced rather than a documentation-level contract,
   and so `analysis_period_basis`'s home — inside the metric object vs. a sibling field — can be
   decided with real schema context) is an open schema-design candidate, not resolved here.

**Explicitly closed by prior review rounds (not open — kept here only as a pointer, full decision
lives in the section cited):** CM≤0 semantics (§6, `NOT_APPLICABLE`, not `OK`+`null`);
`NOT_APPLICABLE`'s module-status interaction (§15, confirmed inert against
`aggregate_module_status()` with zero code change); `break_even_quantity_units` (§8, excluded
entirely from v0.1, not merely deferred in shape); multi-component behavior (§11,
`module_status="ERROR"`, `MULTI_COMPONENT_BEP_NOT_SUPPORTED`, `per_component={}`);
multi-component evaluation priority (§11, STEP 1 gate always short-circuits STEP 2 — no
"simultaneous" evaluation with `INCONSISTENT_FIXED_COST_BASIS` ever occurs); negative
`fixed_operating_cost.amount` (§4, ERROR/`INVALID_NEGATIVE_COST`); the `break_even_quantity_exact.
unit` field's meaning (§4, a quantity-unit label, never the FC basis string); **Contribution
Margin economic primitive extraction — the MODE A/BEP CM aggregation helper (§3/§12,
IMPLEMENTED — `core/engine/economics.py` now holds `price_converted`/`sum_cost_category`/
`DIRECT`/`VARIABLE`, MODE A migrated onto it, BEP calls it directly with zero dependency on
`mode_a.py`)**. Note: this is unrelated to, and does not imply progress on, the actual
shared-cost (`applies_to_component: "shared"`) allocation engine — that remains
`NOT_IMPLEMENTED` everywhere (§12's table is unchanged; "shared" fixed-cost items still resolve
to UNKNOWN/ERROR per the existing canonical/BEP-deviated rules, never a computed allocation
amount). "Contribution Margin economic primitive" here refers strictly to the code-sharing
extraction (one implementation instead of two, in `economics.py`), not to any cost-allocation
capability.
