# Volume Profit (판매량 기반 손익) — SPEC (DRAFT v0.1)

## 0. Status

Design-only. No Python code, schema change, test, Excel, or web work exists yet. This document is
the formula/dependency source of truth for Volume Profit once implementation starts — it plays the
same role `docs/features/bep/SPEC.md` plays for BEP. Anything that conflicts with BEP/MODE A/B/C
semantics is called out explicitly (§12); anything not called out reuses them unchanged.

Every number in the worked example (§14) is a hand calculation, not engine output. It must be
re-derived by tests once the module exists.

## 1. Core question

**"계획 판매량을 팔면 기간 영업이익은 얼마이고, 손익분기 판매량 대비 얼마나 여유가 있는가?"**
— at the component's *current actual price* (MODE A's price basis), if `planned_quantity` units
are sold in the analysis period, what are total net sales, total contribution margin, and
operating profit after `fixed_operating_cost`, and how far above or below the BEP is that plan?

**Why this module exists.** MODE A/B/C are per-unit calculations. BEP is the only module with a
quantity dimension, and it produces quantity as an *output* only (`Q_BEP`). Nothing in the Harness
accepts a quantity as an *input*, so a consultant cannot answer "월 500개 팔면 얼마 남는가" or "지금
물량이 손익분기 대비 안전한가". `docs/features/bep/SPEC.md` §10 deferred exactly this
(`margin_of_safety`, `required_quantity_gap`) until "a quantity-input field is added to the
schema". This module adds that field and the metrics that depend on it, so BEP §10's revisit
condition is met by this document.

**What it does not do.** It does not model demand. `planned_quantity` is an exogenous input, like
MODE C's `target_market_price`; the module never predicts how quantity responds to price. Price
elasticity and demand curves are out of scope (§15).

## 2. Relationship to MODE A / B / C / BEP

| Module | Question | Quantity |
|---|---|---|
| MODE A | 지금 이 가격에서 단위당 얼마가 남는가? | none (per unit) |
| MODE B | 목표 마진을 달성하려면 얼마에 팔아야 하는가? | none |
| MODE C | 시장가격·목표마진에서 원가를 얼마까지 쓸 수 있는가? | none |
| BEP | 손익분기 판매량은? | **output** (`Q_BEP`) |
| **Volume Profit** | **계획 판매량에서 기간 영업이익과 안전한계는?** | **input** (`planned_quantity`) |

Volume Profit is a sibling of BEP, not a layer on top of it. Following BEP's Design 2 decision
(`bep/SPEC.md` §3), `run_volume_profit(client_input)` takes only `client_input`, recomputes
`CMu` and `FC` itself, and never consumes an existing `bep` or `mode_a` result object. It never
defines its own pricing formula for `CMu`; the per-unit economics are MODE A's, unchanged.

## 3. Schema addition (proposed — not yet applied)

One new optional top-level object on `client_input`:

```json
"sales_plan": {
  "planned_quantity": 200,
  "period_basis": "per_month"
}
```

| Field | Type | Meaning |
|---|---|---|
| `planned_quantity` | number or null, `>= 0` | Units sold within the analysis period. `null` = not yet entered. |
| `period_basis` | enum, v0.1 allows only `"per_month"` | The period `planned_quantity` is denominated in. |

**Why `period_basis` is an explicit field and not a convention.** BEP's `Q_BEP` inherits its period
implicitly from `fixed_operating_cost.basis` (`bep/SPEC.md` §4: a documentation-level contract,
listed there as open item 1 and 2 in §18). That is tolerable when the quantity is an *output*.
When the quantity is an *input* a person types, an annual quantity paired with monthly fixed cost
would silently produce a wrong profit. So here the period is stated by the input itself and
cross-validated (§9), which closes that gap for this module without adding a global analysis-period
field.

**Why `per_month` only.** The `cost_item.basis` enum has exactly one period-style value,
`per_month` (the others are per-unit, per-order, per-visit, or rate bases). There is no
`per_year`. Supporting more periods needs a schema change on the cost side too; deferred (§15).

**Schema mechanics.** Top-level `additionalProperties` is `false`, so this is a real schema change:
add `sales_plan` as an optional property, bump `schema_version` `1.1` → `1.2` (additive; every
existing `1.1` document stays valid by omission), and extend `analysis_result.schema.json` with the
new module block. The four version axes in the README move independently: only the schema axis
and the engine marker change; the Excel artifact does not.

**`sales_plan` omitted entirely** → the module is not an error. It reports `status = "NOT_RUN"`
(an existing module-level status) with no metrics, because an absent plan means "the consultant
has not asked this question", not "data is missing". `sales_plan` present with
`planned_quantity: null` is different: that is `UNKNOWN` (§9).

## 4. Symbols and formulas

```
Q    = planned_quantity                      (input, sales_plan)
N    = net_sales_ex_vat per unit             (MODE A's actual_price_ex_vat)
CMu  = contribution_margin_per_unit          (MODE A semantics, bep/SPEC.md §3)
FC   = fixed_operating_cost for the period   (bep/SPEC.md §4/7/12)
Q_BEP = FC / CMu                             (bep/SPEC.md §5, reused unchanged)

total_net_sales_ex_vat      = N   × Q
total_contribution_margin   = CMu × Q
operating_profit            = CMu × Q − FC
operating_profit_rate       = operating_profit / total_net_sales_ex_vat
margin_of_safety_quantity   = Q − Q_BEP
margin_of_safety_rate       = (Q − Q_BEP) / Q
```

All money figures are ex-VAT, in `fx.reporting_currency`. VAT handling is MODE A's, unchanged
(`dependency_rules.md` §2); no VAT-inclusive total is produced (§10).

`operating_profit` follows from `CMu × Q − FC` and is intentionally *not* `Q × (CMu − FC/Q)` or
any per-unit allocation of fixed cost; fixed cost is never spread per unit anywhere in the
Harness, and this module does not start doing so.

## 5. Dependency and status rules

Same discipline as every other module: dependency/status priority is decided **before** any
division or multiplication is attempted, never inferred from a raw exception.

**Gate order (strict, like BEP §11):**

```
STEP 1 — sales_plan absent                    -> module status NOT_RUN, stop.
STEP 2 — more than one price component        -> ERROR, MULTI_COMPONENT_VOLUME_PROFIT_NOT_SUPPORTED,
                                                  per_component = {}, stop.
STEP 3 — (single component only)
         sales_plan field validity (§9), fixed-cost basis (§6), CMu chain, FC chain,
         currency — then the arithmetic in §4.
```

STEP 2 is the same hard gate and rationale as `bep/SPEC.md` §11: shared fixed cost would be
double-counted per component. A multi-component input is a structurally unsupported shape, so it
is `ERROR`, not `UNKNOWN`.

**Metric dependency table:**

| Metric | Needs |
|---|---|
| `planned_quantity` (echo) | `sales_plan.planned_quantity` |
| `total_net_sales_ex_vat` | `Q`, `N` |
| `total_contribution_margin` | `Q`, `CMu` |
| `operating_profit` | `Q`, `CMu`, `FC` |
| `operating_profit_rate` | `operating_profit`, `total_net_sales_ex_vat` |
| `break_even_quantity_exact` | `CMu`, `FC` (identical to BEP) |
| `margin_of_safety_quantity` | `Q`, `break_even_quantity_exact` |
| `margin_of_safety_rate` | `margin_of_safety_quantity`, `Q` |

A metric is `UNKNOWN` if any dependency is `UNKNOWN`, `ERROR` if any is `ERROR` (code
`DOWNSTREAM_*`), per `dependency_rules.md` §1. `null` is never treated as `0`.

## 6. Fixed-cost basis requirement

`FC` is aggregated exactly as BEP does (no item = confirmed `0`; `amount = null` = `UNKNOWN`;
negative = `ERROR INVALID_NEGATIVE_COST`; shared + `blended_only` = `UNKNOWN
FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED`; the rest of `bep/SPEC.md` §12 unchanged).

One addition specific to this module: because `Q` is a count within a *monthly* period, the
contributing fixed-cost items' shared `basis` must be `per_month`.

- No `fixed_operating_cost` item → `FC = 0`, `analysis_period_basis = null`; nothing to
  cross-check, proceed.
- Items share `basis = "per_month"` → proceed.
- Items share any other `basis` (`per_unit_per_month`, `per_visit`, ...) → `ERROR`, code
  `UNSUPPORTED_FIXED_COST_BASIS_FOR_VOLUME`. This is `ERROR`, not `UNKNOWN`: it is a structurally
  unsupported shape, not missing data. In particular `per_unit_per_month` means the cost itself
  scales with quantity, which would make `FC` a function of `Q`; that model is deferred (§15), not
  guessed at.
- Items with mixed `basis` → `ERROR INCONSISTENT_FIXED_COST_BASIS` (BEP's existing code, reused).

## 7. Quantity semantics

- `planned_quantity = null` → `UNKNOWN`, code `MISSING_DEPENDENCY`, dependency
  `sales_plan.planned_quantity`. Every metric needing `Q` is `UNKNOWN` (`DOWNSTREAM_UNKNOWN`).
- `planned_quantity < 0` → `ERROR`, code `INVALID_NEGATIVE_QUANTITY`. Schema `minimum: 0` rejects
  it at validation; the engine still checks it because `run_volume_profit` can be called without
  the validator.
- `planned_quantity = 0` → valid, a real answer ("판매 없음"): `total_net_sales = 0`,
  `total_contribution_margin = 0`, `operating_profit = −FC`. `operating_profit_rate` and
  `margin_of_safety_rate` have a zero denominator, so they are `NOT_APPLICABLE` (inputs known, no
  meaningful value) — not `ERROR`, because `Q = 0` is a legitimate input, not a malformed one.
- Non-integer `Q` is accepted and **never rounded**, for the same reason as `bep/SPEC.md` §8: the
  schema has no discreteness field, and rounding belongs to the presentation layer.

## 8. Margin of safety — sign semantics (differs from BEP on purpose)

BEP forbids negative or zero output (`break_even_quantity_exact` is `NOT_APPLICABLE` for
`CMu ≤ 0`). Margin of safety is the opposite case: **negative is a meaningful answer**, not an
undefined concept.

- `Q > Q_BEP` → `margin_of_safety_quantity > 0`, `OK`.
- `Q = Q_BEP` → exactly `0`, `OK`.
- `Q < Q_BEP` → negative value, **status stays `OK`**, plus non-blocking warning
  `BELOW_BREAK_EVEN` ("계획 판매량이 손익분기 판매량에 못 미칩니다 — 고정운영비를 회수하지
  못합니다."). The value is preserved, never clamped to `0`. This mirrors MODE C's
  `NEGATIVE_ALLOWABLE_COST` precedent (`docs/features/mode_c_allowable_cost/SPEC.md` §8: a negative number from valid
  inputs is `OK` plus a warning).
- `break_even_quantity_exact` is `NOT_APPLICABLE` (`CMu ≤ 0`) → `margin_of_safety_quantity` and
  `margin_of_safety_rate` are `NOT_APPLICABLE` too (no break-even to measure against), carrying a
  non-blocking `BREAK_EVEN_UNDEFINED_*` warning inherited from BEP's matrix (`bep/SPEC.md` §9).
  `operating_profit` is **still computed** in this case: it needs `CMu`, `Q`, `FC`, not `Q_BEP`.
  With `CMu < 0` and `Q > 0` it is simply a loss, which is the correct diagnosis.

## 9. Period cross-validation

- `sales_plan` present but `period_basis` missing → `UNKNOWN`, `MISSING_DEPENDENCY`, dependency
  `sales_plan.period_basis`. A quantity without a stated period is not usable, and this module
  does not assume monthly (BEP §4's same refusal).
- `period_basis` not `"per_month"` (cannot occur if the schema is enforced; checked anyway) →
  `ERROR`, `UNSUPPORTED_PLAN_PERIOD`.
- `period_basis` must equal the fixed-cost `analysis_period_basis` when both exist. A difference
  is `ERROR`, code `PERIOD_BASIS_MISMATCH`. With §6 this is only reachable via a future
  multi-period expansion, but the check is specified now so adding a period later cannot silently
  create a mismatch.

## 10. VAT, currency, and what is not produced

- **No VAT-inclusive totals.** `total_gross_payment_incl_vat` is not a metric, for the same reason
  `bep/SPEC.md` §9 excludes break-even revenue figures: it is `Q × G`, derivable by any consumer
  from `planned_quantity` and MODE A's `G`, and it would reopen the VAT-basis disambiguation for
  no new information.
- **Currency** is unchanged from MODE A/BEP: `FC`, `N`, `CMu` all land in
  `fx.reporting_currency` via `common.convert_to_reporting()`. `planned_quantity` is a count and
  has no currency.

## 11. Per-order costs — the one assumption this module introduces

MODE A treats every amount-valued direct/variable cost as a per-unit figure, including items whose
`basis` is `per_order`. For a single transaction that was harmless. Here it matters: the module
multiplies `CMu` by `Q`, so a `per_order` shipping cost of 3,000 is multiplied by the number of
*units*. If customers buy more than one unit per order, shipping is **overstated** and operating
profit **understated**. The schema has no `units_per_order` field.

**Decision: use the existing `ESTIMATED` metric status; do not silently proceed and do not
block.** If any contributing `product_service_direct_cost` or `variable_selling_delivery` item has
`basis = "per_order"`, then every metric that depends on `CMu × Q` (`total_contribution_margin`,
`operating_profit`, `operating_profit_rate`, `break_even_quantity_exact`,
`margin_of_safety_quantity`, `margin_of_safety_rate`) is reported with status `ESTIMATED` and a
non-blocking warning `ASSUMES_ONE_UNIT_PER_ORDER` ("per_order 비용을 주문당 1개 판매로
가정했습니다. 주문당 구매 수량이 1개보다 크면 비용이 과대 계상됩니다.").

`ESTIMATED` already exists in `metric_status` ("computed from an assumed/default value rather than
a confirmed input") and `aggregate_module_status()` treats it like `OK` (neither `ERROR` nor
`UNKNOWN`), so no change to `common.py` is needed. **This would be the first use of `ESTIMATED`
by any implemented module** (`mode_a.py` notes it is part of the enum but never produced), so
the implementation must confirm the status propagates through `result_builder` and the result
schema without special-casing. Flagged as an open item (§16) rather than assumed.

`break_even_quantity_exact` is `ESTIMATED` in this module even though BEP itself reports `OK` for
the same input: BEP's `Q_BEP` is the same arithmetic, so the *value* is identical, but this module
is the one that states the assumption because it is where the unit-versus-order distinction
becomes visible to the reader. Whether BEP itself should carry the same warning is a separate
decision not made here (§16).

## 12. Deviations from, and reuse of, existing rules

| Rule | Treatment |
|---|---|
| `CMu` aggregation (MODE A semantics) | reused unchanged, via `core/engine/economics.py` |
| `FC` aggregation (BEP rules incl. `blended_only` → `UNKNOWN`) | reused unchanged semantics; see implementation note below |
| Multi-component hard gate | same rule, new code `MULTI_COMPONENT_VOLUME_PROFIT_NOT_SUPPORTED` |
| Negative result handling | **deviates from BEP**: negative margin of safety is `OK` + warning (§8), because it is meaningful |
| `ESTIMATED` status | **new use** (§11) |
| Module status | canonical 3-tier via `aggregate_module_status()`, unchanged |

**Implementation note — extracting `_sum_fixed_operating_cost`.** BEP SPEC §12 kept
`fixed_operating_cost` aggregation BEP-local on purpose, because BEP was its only consumer and
folding its `blended_only` deviation into the shared function would have made `economics.py`
carry BEP-specific policy. This module is a second consumer of exactly that logic. Duplicating it
would create two implementations of a rule that must never drift, which is the problem
`economics.py` was introduced to prevent for MODE A and BEP. The expected implementation is to
move `_sum_fixed_operating_cost` into `economics.py` unchanged (BEP's behavior and tests must stay
byte-identical) and have both modules call it. This is a refactor: the full existing `pytest` suite and
the BEP Excel QA must keep passing unchanged, and it is listed in §16 to be confirmed at
implementation time.

## 13. Output metrics — v0.1 core set

```
planned_quantity             (echo of sales_plan.planned_quantity; unit "units")
total_net_sales_ex_vat       (money)
total_contribution_margin    (money)
operating_profit             (money; may be negative)
operating_profit_rate        (ratio; NOT_APPLICABLE when total net sales = 0)
break_even_quantity_exact    (units; same value and NOT_APPLICABLE rules as BEP)
margin_of_safety_quantity    (units; may be negative)
margin_of_safety_rate        (ratio; NOT_APPLICABLE when Q = 0)
```

Block shape mirrors `bep`: `{ status, per_component, warnings }`, with `analysis_period_basis`
carried per component exactly as BEP does. Result block name: `volume_profit`. Module-level status
vocabulary is unchanged: `OK`, `INCOMPLETE`, `ERROR`, `NOT_RUN`, `NOT_IMPLEMENTED`.

## 14. Worked example (hand calculation — to be verified by tests)

Inputs: price 35,000 KRW VAT-inclusive, VAT 10 %, direct cost 12,000 + 1,500, PG fee 2.5 % of
gross payment, shipping 3,000 `per_order`, fixed operating cost 2,000,000 `per_month` on this
component (component-scoped, **not** `shared`/`blended_only`, otherwise `FC` is `UNKNOWN` per §6),
`planned_quantity = 200`, `period_basis = per_month`.

```
N     = 35,000 / 1.10                   = 31,818.18
CMu   = 31,818.18 − 13,500 − (3,000 + 0.025 × 35,000) = 14,443.18
Q_BEP = 2,000,000 / 14,443.18           ≈ 138.47 units

total_net_sales_ex_vat    = 31,818.18 × 200            = 6,363,636
total_contribution_margin = 14,443.18 × 200            = 2,888,636
operating_profit          = 2,888,636 − 2,000,000      = 888,636
operating_profit_rate     = 888,636 / 6,363,636        ≈ 13.96 %
margin_of_safety_quantity = 200 − 138.47               ≈ 61.53 units
margin_of_safety_rate     = 61.53 / 200                ≈ 30.76 %
```

Because shipping is `per_order`, the metrics that use `CMu × Q` carry status `ESTIMATED` and
warning `ASSUMES_ONE_UNIT_PER_ORDER` (§11). At `Q = 100` the same example gives
`operating_profit ≈ −555,682` (status `OK`/`ESTIMATED` per §11) and
`margin_of_safety_quantity ≈ −38.47` with warning `BELOW_BREAK_EVEN`.

The shipped sample `01_simple_one_time_product.json` has its fixed cost as `shared` +
`blended_only`, so BEP and this module would both report `UNKNOWN` on it today — a new example
Client Input with a component-scoped fixed cost is required to exercise the `OK` path (the same
situation `bep/SPEC.md` §12 documents).

## 15. Scope exclusions (v0.1)

Not in this phase, design or implementation: Python code, schema/Excel/web changes, tests,
commits, demand or price-elasticity modeling, `target_operating_profit` and the inverse question
"목표 이익을 위한 필요 판매량", multi-component / blended sales-mix profit (§5 gate), quantity-
dependent fixed cost (`per_unit_per_month`, step-fixed capacity cost), volume-tiered unit cost or
volume discounts, periods other than `per_month`, a `units_per_order` field, `total_gross_
payment_incl_vat` (§10), Scenario Compare integration (a scenario overriding `planned_quantity`
is the natural next step, but needs its own SPEC revision), and a real shared-cost allocation
engine (still `NOT_IMPLEMENTED` everywhere).

## 16. Open design items (explicit, not silently resolved)

1. **`units_per_order`.** The `ESTIMATED` workaround (§11) is an honest stopgap, not a fix.
   Whether to add the field, and whether it belongs to the price component or to each cost item,
   is undecided.
2. **First use of `ESTIMATED`.** Confirm at implementation that `result_builder.py`,
   `analysis_result.schema.json`, and the Excel/consumers all handle it; no module has emitted it
   before.
3. **Should BEP carry `ASSUMES_ONE_UNIT_PER_ORDER` too?** Today BEP reports `OK` for the same
   `per_order` input (§11). Changing BEP is a behavior change to an implemented, tested module and
   is not made here.
4. **Extraction of `_sum_fixed_operating_cost` into `economics.py`** (§12). Recommended, but it is
   a refactor of BEP-adjacent code and must be validated against BEP's existing tests.
5. **Quantity-dependent fixed cost** (§6, `per_unit_per_month`). Rejected as `ERROR` for v0.1;
   modeling it requires deciding how `FC(Q)` interacts with `Q_BEP = FC / CMu`, which becomes
   circular if `FC` depends on `Q`.
6. **Multi-period support.** Needs a `per_year` (or similar) cost basis in the schema first.
7. **Schema version.** `1.1` → `1.2` is proposed as additive-only; confirm no consumer pins `1.1`
   strictly (the four-axis version table in README treats schema version as a data-compatibility
   marker, so this is a deliberate bump, not a side effect).

## 17. Master Note boundary

Same boundary as `bep/SPEC.md` §16. The Master Note (MN07, primary) motivates the *framing* that
feasibility is judged "at a specific price and quantity"; it does **not** define operating profit,
margin of safety, or any status/dependency rule in this document.
`docs/methodology/MASTER_NOTE_MAPPING.md` states for BEP that the standard formula is absent from
the Reference, and the same holds here. This entire document is Pricing Harness Internal
Specification — do not describe any formula or rule above as something the Master Note defines.
