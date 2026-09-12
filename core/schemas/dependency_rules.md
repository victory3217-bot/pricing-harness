# Dependency & Status Rules

These rules govern how the Pricing Engine (`core/engine/`, built in a later step) turns a
Client Input into an Analysis Result. They are normative for that implementation — written
now, ahead of the code, so the engine has a single spec to follow.

## 1. General propagation rule

A metric is `OK` only if **every** value it depends on is known (a real number, including
an explicit `0`). If any dependency is `null` (UNKNOWN) or itself resolves to `UNKNOWN`/`ERROR`,
the metric is `UNKNOWN` — never silently treated as `0` and never partially summed from only
the known pieces.

Every non-`OK` metric must have at least one corresponding entry in the module's `warnings[]`,
with `dependency_paths` naming the exact field(s) responsible.

## 2. VAT dependency is conditional, not blanket — and applies symmetrically to net sales AND gross payment

**Terminology**: `selling_price` = the raw `price_component.actual_price` field as entered.
`net_sales_ex_vat` (N) = the VAT tax base (MODE A's `actual_price_ex_vat`). `gross_payment_incl_vat`
(G) = what the customer actually pays. In a standard taxable transaction, **`G = N × (1 + v)`
always** — this economic relationship does not depend on which of the two `selling_price`
happens to represent. `price_includes_vat` only says which one `selling_price` *is*; it never
makes VAT rate irrelevant to computing the *other* one.

`net_sales_ex_vat` depends on `price_includes_vat` and, conditionally, on `tax.vat_rate`:

| `price_includes_vat` | `vat_rate` | `net_sales_ex_vat` |
|---|---|---|
| `null` (unknown) | any | **UNKNOWN** — we don't even know if VAT is embedded in the price |
| `true` | `null` | **UNKNOWN** — price includes VAT but we don't know the rate to back it out |
| `true` | number | **OK** — `selling_price / (1 + vat_rate)` |
| `false` | `null` | **OK** — price already excludes VAT; `net_sales_ex_vat = selling_price`, rate irrelevant here |
| `false` | number | **OK** — same as above; `vat_rate` is simply unused for *this* metric |

`gross_payment_incl_vat` is the **mirror** of the above — the branch that needs `v` is the
opposite one:

| `price_includes_vat` | `vat_rate` | `gross_payment_incl_vat` |
|---|---|---|
| `null` (unknown) | any | **UNKNOWN** — same reason as above |
| `true` | any | **OK** — `gross_payment_incl_vat = selling_price`, rate irrelevant here |
| `false` | `null` | **UNKNOWN** — price excludes VAT but we don't know the rate to gross it up |
| `false` | number | **OK** — `selling_price × (1 + vat_rate)` |

**This is the rule an earlier version of this document got wrong**: it stated that
`price_includes_vat = false` makes `vat_rate` irrelevant *in general*. That is only true for
`net_sales_ex_vat`. A `rate_of_gross_payment` cost item still needs `gross_payment_incl_vat`,
which under `price_includes_vat = false` requires `vat_rate` to be known. Whether `vat_rate` is
actually needed is a **per-metric** question — never decide it once for the whole component.
The one case that must **not** cause a blanket UNKNOWN of everything: a single null field
(`vat_rate` or otherwise) only propagates to the metrics that actually depend on it.

## 3. Direct cost vs. variable cost vs. fixed cost

- `cost_category = product_service_direct_cost` → included in `direct_cost_total`, which feeds
  `gross_profit`.
- `cost_category = variable_selling_delivery` → included in `variable_cost_total`, which feeds
  `contribution_margin` **on top of** `gross_profit`. Not part of Gross Profit.
- `cost_category = fixed_operating_cost` → excluded from both. Used only by `bep` (not yet
  implemented).

Default classification: **installation cost is `variable_selling_delivery`**, not a direct
product cost, under this Harness's convention — even though it is a one-time, per-unit cost.
A client's own cost accounting policy may justify reclassifying it as
`product_service_direct_cost`; this is a per-engagement decision, not a schema constraint.

## 4. Shared cost allocation

A cost item with `applies_to_component = "shared"` cannot be assigned to a single component's
metrics without a rule. `allocation_rule` decides how:

- `direct` — **CANONICAL RULE (all modes): semantic contradiction, always `ERROR`.** Read
  literally, `applies_to_component = "shared"` means "not attributed to one component" while
  `allocation_rule = "direct"` means "already attributed to a specific component" — the two
  claims contradict each other, and no consumer of this schema may guess which one the author
  meant. Every implemented mode reports the affected aggregate as `ERROR` (code
  `INVALID_ALLOCATION_CONFIGURATION`, dependency path `costs.items[<item_id>].allocation_rule`)
  rather than silently using the item as-is — applying it to every reader would double-count a
  genuinely shared cost, applying it to none would understate it. (An earlier version of this
  document let MODE A treat `direct` on a shared item as "use as-is"; that reading is retired —
  see `core/engine/modes/mode_a.py`'s `_sum_cost_category`, which now agrees with MODE B.)
- `by_component_revenue` — split proportionally to each component's revenue share. Not yet
  resolvable without the (not-yet-built) blended engine — affected aggregate is `UNKNOWN`
  (dependency path `blended.allocation[<item_id>]`), never treated as 0.
- `fixed_share` — split by a fixed ratio configured elsewhere (engine config, not yet defined).
  Same `UNKNOWN` treatment as `by_component_revenue` above.
- `blended_only` — never allocated to an individual component; appears only in the future
  `blended` (whole-contract) block. Legitimately excluded at component level — no warning.
- missing or unrecognized `allocation_rule` on a `shared` item — `UNKNOWN`, dependency path
  `costs.items[<item_id>].allocation_rule`.

Per-component `variable_cost_total` / `fixed_cost_total` for a `shared` item with
`allocation_rule` other than `blended_only` therefore also depends on the *other* components'
revenue (for `by_component_revenue`) — this is itself a dependency and must be reflected in
`dependency_paths` when incomplete.

## 5. Metric status vs. module status

- **Metric status** (`OK` / `UNKNOWN` / `ESTIMATED` / `NOT_APPLICABLE` / `ERROR`) belongs only
  inside a `{value, status, unit}` object.
- **Module status** (`NOT_IMPLEMENTED` / `NOT_RUN` / `INCOMPLETE` / `OK` / `ERROR`) belongs only
  on a block's own top-level `status` (e.g. `mode_a.status`). `NOT_IMPLEMENTED` must never appear
  as a metric status.

**Canonical 3-tier rule (module status, all implemented modes):**

1. Every metric that applies is `OK` (or `NOT_APPLICABLE`) → module `OK`.
2. No metric is `ERROR`, but at least one is `UNKNOWN` → module `INCOMPLETE`.
3. At least one metric is `ERROR` → module `ERROR`. **`ERROR` outranks `UNKNOWN`** — a module
   with both an `ERROR` metric and an unrelated `UNKNOWN` metric (e.g. across two components) is
   still `ERROR`, not `INCOMPLETE`.

This supersedes an earlier version of this rule that collapsed `UNKNOWN` and `ERROR` into a
single `INCOMPLETE` tier — that version under-reported genuine calculation failures (a
denominator ≤ 0, an invalid shared+direct configuration) as merely "missing data," when they are
a confirmed, data-independent failure the consultant needs to see distinctly. Implemented via
`core/engine/common.py`'s `aggregate_module_status()`, shared by every mode.

## 6. MODE C — allowable-cost specifics

See `docs/features/mode_c_allowable_cost/SPEC.md` for the full derivation and rationale; this
section records only the rules that are canonical (binding on the implementation) and not
already covered by §1-§5 above.

**Canonical market-price source**: `product.price_components[].target_market_price` —
per-component, sharing that same component's `price_includes_vat`/`currency` (fed into
`common.resolve_price_basis()` exactly like MODE A's `actual_price`). `targets.target_market_price`
does not exist in the schema (removed — an earlier draft placed a global scalar there; no engine
ever read it, and it could not represent a different market price per component). MODE C has no
fallback to any other field — a missing `target_market_price` is UNKNOWN, full stop.

**`ADC = N(1 − t − b) − aG − F` — `allowable_direct_cost` is never a dependency of anything, and
depends on nothing from `actual_direct_cost`.** `product_service_direct_cost` items are read
**only** to compute `actual_direct_cost`/`direct_cost_gap`; `allowable_direct_cost` never reads
them. Symmetrically, a shared-cost problem on a `variable_selling_delivery` item (feeding
`F`/`b`/`a`) propagates to `allowable_direct_cost` (and therefore
`expected_contribution_margin[_rate]`) but never to `actual_direct_cost`; a shared-cost problem
on a `product_service_direct_cost` item propagates to `actual_direct_cost`/`direct_cost_gap` but
never to `allowable_direct_cost`. Do not merge these two aggregations' dependency paths.

**Negative `allowable_direct_cost` is `OK`, not `ERROR`, and is never clamped to 0.** Unlike
MODE B's `N = C/D` (division — `D ≤ 0` is genuinely non-computable), MODE C's `ADC = N·D − F` is
multiplication — every combination of known, valid inputs produces one well-defined real number,
including a negative one. A negative result means "even a direct cost of zero cannot reach the
target margin at this price/fee structure" — a confirmed, valid answer, not a failure. Attach a
non-blocking warning (`severity: "warning"`, code `NEGATIVE_ALLOWABLE_COST`) instead.

## 7. BEP — break-even specifics

See `docs/features/bep/SPEC.md` for the full derivation and rationale; this section records only
the rules that are canonical (binding on the implementation) and not already covered by §1-§6
above.

**`Q_BEP = FC / CMu`. `CMu` (`contribution_margin_per_unit`) uses MODE A's Contribution Margin
semantics exactly** (`net_sales_ex_vat − product_service_direct_cost − variable_selling_delivery
costs`; `fixed_operating_cost` excluded) — recomputed independently from the same Client Input
BEP receives, never consumed from an existing `mode_a` result object (uniform `run_bep
(client_input)` signature, matching `mode_a`/`mode_b`/`mode_c`).

**`fixed_operating_cost` (`FC`) aggregation follows the same no-item/null/explicit-zero rule as
every other cost aggregation in this document (§1)** — no matching `cost_category:
fixed_operating_cost` item for the component is a confirmed `0` (`OK`), a matching item with
`amount = null` is `UNKNOWN`, and `amount = 0` (explicit) is `OK`. **New rule, BEP-only:** a
matching item with `amount < 0` is `ERROR`, code `INVALID_NEGATIVE_COST` — no mode before BEP
ever needed a sign rule for this field, since none of them read `fixed_operating_cost` at all.

**Shared `fixed_operating_cost` reuses the canonical shared-cost classification (§4) with one
deliberate deviation**: `applies_to_component: "shared"` + `allocation_rule: "blended_only"` is
`UNKNOWN` for BEP (code `FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED`), **not** the "excluded,
contributes 0, no warning" treatment §4 specifies for every other mode. That "excluded" behavior
was only ever safe because MODE A/B/C never read `fixed_operating_cost` in the first place
(filtered out by `cost_category` before shared-classification even matters to them) — BEP's
numerator *is* that cost category, so reusing "excluded" verbatim would silently zero out real
fixed-cost data. The other three `shared` branches (`direct` → `ERROR`,
`INVALID_ALLOCATION_CONFIGURATION`; `by_component_revenue`/`fixed_share`/unrecognized →
`UNKNOWN`, `UNSUPPORTED_SHARED_COST_ALLOCATION`) are unchanged from §4.

**`analysis_period_basis`** (`analysis_result.bep.per_component[].analysis_period_basis`) is the
single `cost_item.basis` every contributing `fixed_operating_cost` item shares — period context
for `break_even_quantity_exact`, never itself a quantity unit. Contributing items with differing
`basis` values make `fixed_operating_cost` `ERROR` (code `INCONSISTENT_FIXED_COST_BASIS`), not a
silent pick of one. When no `fixed_operating_cost` item exists for the component at all,
`analysis_period_basis` is `null` (there is no period context to state — this is distinct from,
and must not be confused with, an UNKNOWN/ERROR fixed-cost status; `fixed_operating_cost` itself
is a confirmed `0`, `OK`, in this case per the no-item rule above).

**`break_even_quantity_exact.unit` is always a quantity-unit label (e.g. `"units"`) — never a
basis/period string.** Conflating the two (using the FC `basis` as the metric's `unit`) is an
explicitly rejected design (`docs/features/bep/SPEC.md` §4).

**`contribution_margin_per_unit ≤ 0` makes `break_even_quantity_exact` `NOT_APPLICABLE`
(`value: null`), never a plain `OK` with a `null`/`0` value, and never `UNKNOWN`/`ERROR`.** All
inputs are known and the computation is well-defined arithmetically; there is simply no
meaningful break-even quantity to report (CMu=0: no finite quantity recovers FC; CMu<0: more
sales strictly worsen the loss). `NOT_APPLICABLE` does not affect module status (§5's canonical
3-tier rule already treats any non-`ERROR`/non-`UNKNOWN` metric status, `NOT_APPLICABLE`
included, as not lowering module status — no change to `aggregate_module_status()` was needed).
The full FC×CMu sign matrix (all four combinations of `FC∈{=0,>0}` × `CMu∈{>0,=0,<0}`), including
the requirement that `FC=0, CMu<0` must still report `NOT_APPLICABLE` rather than the
raw-arithmetic `0`, is specified in `docs/features/bep/SPEC.md` §9 — never output a `0` or
negative `break_even_quantity_exact` for any `CMu ≤ 0` case.

**Multi-component `client_input` (`product.price_components` count > 1) is an unconditional hard
gate, evaluated before anything else.** `bep.status = "ERROR"`, code
`MULTI_COMPONENT_BEP_NOT_SUPPORTED`, `bep.per_component = {}` — no fixed-cost, CM, currency, or
shared-allocation evaluation is attempted for any component in this case, not even partially.
This is `ERROR`, not `UNKNOWN`: a multi-component input is not missing data that could resolve
itself with more input, it is a structurally unsupported shape for this module version (BEP v0.1
= single-component only, per `docs/features/bep/SPEC.md` §11 — computing a naive per-component
`FC_i / CM_i` would double-count any shared fixed cost across components). This gate strictly
precedes — and, when it fires, entirely replaces — every other BEP validation in this section;
e.g. an inconsistent `fixed_operating_cost` basis on a multi-component input is never itself
evaluated or reported once the gate has already fired.
