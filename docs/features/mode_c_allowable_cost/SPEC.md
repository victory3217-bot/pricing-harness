# MODE C — Allowable Direct Cost — SPEC (DRAFT v0.1, design only — no code written)

Status: **design draft — no code, no schema changes, no tests**. This document is for review
before `core/engine/modes/mode_c.py` is started. Every formula and dependency rule here follows
the same discipline already established and implemented in MODE A/B (see
`core/schemas/dependency_rules.md`, `core/engine/common.py`) — no new semantic is introduced
without an explicit reason called out below.

## Question answered

> 시장가격과 목표 Contribution Margin Rate가 주어졌을 때, 허용 가능한 최대 product/service
> direct cost는 얼마인가?

## MODE A / B / C relationship (role boundary)

| Mode | Given | Solves for |
|---|---|---|
| MODE A | current price, current cost structure | current Gross Profit / Contribution Margin (diagnosis) |
| MODE B | current cost structure, target CM rate | the price that hits the target (price is the unknown) |
| MODE C | **market price** (externally given, not computed), non-product variable costs, target CM rate | the maximum `product_service_direct_cost` the business can still afford (**cost is the unknown, price is not**) |

MODE C does not price anything. The selling price is exogenous — set by the market, a
competitor's price, or a client's existing price point — and MODE C never recomputes or
suggests it. What MODE C answers is a **target costing** question: given that price and a
required profitability, how much room is left for direct cost.

## Source boundary (Master Note vs. Internal Specification)

Consistent with MODE A/B's boundary (see `docs/methodology/MASTER_NOTE_MAPPING.md` and each
mode's own SPEC §"Source boundary"): the Reference attributes to the Master Note the *concepts*
that MODE C is a direct application of — pricing decisions driven by customer value/market/
competition rather than cost alone, the Contribution Margin lens, and the general idea of
"target costing" (working backward from an acceptable margin to an acceptable cost). **The
Reference does not define a concrete algebraic formula for inverting a target Contribution
Margin Rate into an allowable direct cost.** Every formula in this document — the symbols
(N/G/t/b/a/F/ADC), the derivation in §3, the dependency rules in §6, and every UNKNOWN/ERROR
rule — is **Category B, Pricing Harness Internal Specification**, exactly as MODE B's formula
is. It must never be presented as "Master Note가 정의한 공식."

## 1. Inputs

### 1a. Market selling price — input source decision (revised)

**An earlier draft of this document recommended reusing
`product.price_components[].actual_price` for MODE C's market price. That recommendation is
withdrawn and replaced below** — it could not represent the ordinary case where a client's
*current* actual price and the *market* price MODE C must target-cost against are simply
different numbers (e.g. `actual_price = 90,000` today, while the market has moved to
`100,000`). A single scalar field cannot hold both at once, and MODE A/B/C are meant to run over
one shared Client Input, so this was a real structural gap, not a cosmetic one.

**Current schema, re-read directly from `client_input.schema.json`:**

```json
"targets": {
  "type": "object",
  "additionalProperties": false,
  "description": "Reserved for MODE B / MODE C (not implemented yet). Always valid to leave both null.",
  "properties": {
    "target_contribution_margin_rate": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
    "target_market_price": { "type": ["number", "null"] }
  }
}
```

- **Type**: `["number", "null"]` — a bare scalar, no nested structure.
- **Null allowed**: yes (`null` = UNKNOWN, per this Harness's universal convention).
- **Unit/currency**: **none defined**. No `currency` sibling field, no reference to
  `fx.reporting_currency` or `fx.base_currency` in its description.
- **Scope**: **global**, not per-component — it sits directly under the top-level `targets`
  object (a sibling of `target_contribution_margin_rate`), not inside
  `product.price_components[]`. One Client Input has at most one `target_market_price`, no
  matter how many price components it has.
- **Description**: `"Reserved for MODE B / MODE C (not implemented yet). Always valid to leave
  both null."` — explicitly reserved, no other semantics documented.
- **Actually used by any implemented mode**: **no.** Confirmed by search — `mode_a.py` and
  `mode_b.py` never reference it; every checked-in example and test sets it to `null` as a
  placeholder only.

**Why `actual_price` reuse fails**: `actual_price` is a single value per component. MODE A's
diagnostic use of it ("what does today's price earn") and MODE C's target-costing use of it
("given this price, what can cost be") would have to be the *same number* in the same Client
Input if MODE A and MODE C ran together — but the whole point of MODE C is often to answer "the
market has moved / we're pricing a new product at a market reference point that differs from
what we currently charge." Overloading one field cannot represent that scenario at all, so
Option A is not a documentation nuance to manage (as the earlier draft treated it) but an actual
modeling gap.

**Why `target_market_price` as it exists today is not directly usable either**: it has no VAT
basis (`price_includes_vat`) or `currency` of its own, and it is global while MODE C's output is
per-component (§11) — a multi-component product (e.g. hardware + SaaS) needs a different market
price per component, which one global scalar cannot hold.

**v0.1 recommendation — a new per-component field, inheriting VAT/currency context from the
same component it lives in:**

```
product.price_components[].target_market_price   (new field, type ["number", "null"])
```

Placed as a sibling of `actual_price` inside the *same* `price_component` object — not under
global `targets`. This means:

- It automatically shares that component's existing `price_includes_vat` and `currency` —
  no new VAT-basis or currency field is needed, because it lives in the same object those
  already describe. `actual_price = 90,000` and `target_market_price = 100,000` coexist in the
  same component, both interpreted through that one component's `price_includes_vat`.
- Multi-component products get a distinct market price per component for free — no ambiguity,
  no forced "single-component only" restriction (§1c below).
- `actual_price` stays exclusively MODE A's field, with its original, undisturbed meaning.
  MODE C never reads `actual_price` at all.
- This **is** a schema change (one new nullable field per `price_component`) — smaller than
  extending `targets.target_market_price` to a per-component map (§1c, Option C) and smaller
  than any structure that would still need a separate VAT-basis/currency field bolted on.
  Deferred to MODE C's actual implementation step, per this round's instruction not to touch
  schema/code yet — recorded here as the decision, not yet applied.

**`targets.target_market_price` (the existing global field) — legacy/reserved, scheduled for
removal when MODE C's schema is implemented.** MODE C never reads it, under any circumstance —
no fallback logic will be written to consult it if `price_components[].target_market_price` is
absent. Two same-named-in-spirit price fields (one global, one per-component) coexisting would
invite exactly the "which one does MODE C actually read" confusion this decision exists to
avoid, and no engine has ever read the global field (confirmed by search — `mode_a.py`,
`mode_b.py` never reference it; every checked-in example/test sets it to `null` as an unused
placeholder only). At MODE C's actual implementation step, `targets.target_market_price` is to
be **removed from `client_input.schema.json`**, not merely left unused — this document records
that as the decision; the removal itself is deferred to that implementation step, same as the
new field's addition.

### 1b. `global vs. component-level` — options compared (§3 of the review)

| Option | Description | Verdict |
|---|---|---|
| **A. Single-component only for v0.1** | Keep `targets.target_market_price` (global) as-is; restrict MODE C to single-`price_component` Client Inputs, document the limitation (mirroring MODE B's already-accepted global-`target_contribution_margin_rate` limitation, §11). | Rejected for the *price* field specifically — MODE C's stated purpose explicitly includes hybrid/multi-component products (the SPEC's own MODE A/B/C table never scoped MODE C to single-component), and this would silently break the moment MODE C model is asked about a hardware+SaaS product with two different market prices. Cheapest option, but too restrictive to be the v0.1 default. |
| **B. Extend to component-level (chosen)** | Add `price_components[].target_market_price`, per §1a. | **Selected.** Solves both the actual-vs-market divergence problem and the multi-component problem with a single, minimal, well-precedented field (this Harness already places `actual_price`/`price_includes_vat`/`currency`/`discount_rate` inside each `price_component`). |
| **C. `targets.per_component` map/array** | Add a new nested structure under `targets` keyed by `component_id`, e.g. `targets.per_component[component_id].market_price`. | Rejected as over-engineering for this need — it duplicates the component-keying `price_components[]` already provides, adds a second place to look up "which component does this apply to," and does not obviously extend better to a *future* per-component `target_contribution_margin_rate` (§11's open item) than simply also giving `price_components[]` its own optional target-rate override field would, if that is ever needed. Option B is the smaller, more consistent change. |

### 1c. Full input list

- `product.price_components[].target_market_price` — **new field, canonical MODE C price source
  (§1a)**: the externally-given, **effective (post-discount) transaction selling price** (§1d)
  — not a list price. Requires a schema change at implementation time — not applied in this
  documentation-only step. MODE C reads this field and **only** this field for its market price;
  `targets.target_market_price` (legacy, §1a) is never consulted, with no fallback.
- `product.price_components[].price_includes_vat` — same field, now also governing
  `target_market_price`'s VAT basis (not just `actual_price`'s).
- `product.price_components[].currency`
- `tax.vat_rate`
- `targets.target_contribution_margin_rate` — same field MODE B reads; still global per Client
  Input, not per-component (see §11 — this limitation is unchanged by §1a/§1b's decision, which
  only concerns the *price* input, not the target rate).
- `costs.items[]` filtered to `cost_category = variable_selling_delivery` (feeds F/b/a, §5) and,
  separately, `cost_category = product_service_direct_cost` (feeds `actual_direct_cost` only,
  §9 — never feeds the allowable-cost formula itself; see §9's dependency-isolation table).
- `fx.*` — currency conversion, via `common.convert_to_reporting()`.

### 1d. `target_market_price` is the effective (post-discount) transaction price — not a list price

**Confirmed meaning (v0.1): `target_market_price` = the price the customer actually pays per
unit/transaction, discount already applied if any exists.** Not a pre-discount list price.

```
market list price   = 100,000
expected discount    = 10%
target_market_price  = 90,000   <- this is what MODE C reads
```

`price_includes_vat` describes whether *this effective price* is VAT-inclusive or -exclusive —
it says nothing about discounting, which is already resolved by the time the number reaches
MODE C.

**`discount_rate` (MODE B's field) is not read or applied by MODE C v0.1.** MODE B inverts
`required_selling_price` (also an effective, post-discount price) into `required_list_price`
using `discount_rate`, because MODE B's job is to hand back a number a price *tag* can show.
MODE C has no equivalent output — it never produces or needs a list price, so there is nothing
for `discount_rate` to invert. If a future engagement needs MODE C to reason about a market
*list* price instead of an effective one, that is a v0.2 addendum requiring its own design
(likely reusing MODE B's `discount_rate` inversion in reverse), not resolved here. Out of scope;
see §11.

### 1e. Price-field semantics across MODE A / B / C — summary

All three modes' price fields are **effective, post-discount, per-unit/transaction prices** —
none of them is ever a pre-discount list price, except `required_list_price`, which MODE B
computes specifically *as* the list-price inversion of an effective price.

| Mode | Field | Meaning |
|---|---|---|
| MODE A | `actual_price` | 현재 실제 판매가격 (effective, 할인 이미 반영된 실거래가) |
| MODE B | `required_selling_price` (output) | 목표 CM 달성을 위한, 할인 후 필요 판매가격 (effective) |
| MODE B | `required_list_price` (output) | 할인 전 정가 — `required_selling_price`를 `discount_rate`로 역산 |
| MODE C | `target_market_price` (input, §1a-§1d) | 외생적으로 주어진, 할인 후 effective market selling price |

The common thread: `actual_price`, `required_selling_price`, and `target_market_price` are all
the *same kind* of number (an effective transaction price) read or produced by a different mode.
Only MODE B additionally produces a list-price view, because only MODE B's business question
("what should the price tag say") needs one.

## 2. Symbols

| Symbol | Meaning | Client Input source |
|---|---|---|
| `N` | `net_sales_ex_vat` — market price, VAT excluded | derived, §4 |
| `G` | `gross_payment_incl_vat` — market price, what the customer actually pays | derived, §4 |
| `t` | target Contribution Margin Rate | `targets.target_contribution_margin_rate` |
| `b` | sum of `rate_of_net_sales` rates, **variable_selling_delivery items only** | `costs.items[]` |
| `a` | sum of `rate_of_gross_payment` rates, **variable_selling_delivery items only** | `costs.items[]` |
| `F` | sum of amount-valued (fixed-amount) `variable_selling_delivery` items | `costs.items[]` |
| `ADC` | `allowable_direct_cost` — the metric MODE C solves for | derived |
| `v` | `tax.vat_rate` | `tax.vat_rate` |

`F`, `b`, `a` are **exactly** MODE B's `C`, `b`, `a` restricted to `variable_selling_delivery`
only — `product_service_direct_cost` is deliberately excluded from all three (§5). This is the
one structural difference from MODE B's cost aggregate: MODE B's `C` includes direct cost
because it is solving for price given a known total cost; MODE C is solving for the direct-cost
*budget itself*, so direct cost cannot be baked into an input.

## 3. Derivation (verified)

Contribution Margin, using the same identity every mode in this Harness starts from:

```
CM = N − ADC − F − bN − aG
```

Setting `CM / N = t` and solving for `ADC`:

```
N − ADC − F − bN − aG = tN
−ADC = tN − N + bN + aG + F
ADC = N(1 − t − b) − aG − F
```

Since `G = N(1 + v)` always (dependency_rules.md §2), this can be rewritten entirely in terms of
`N`:

```
ADC = N[1 − t − b − a(1+v)] − F
```

**Note the resemblance to MODE B**: the bracketed term `1 − t − b − a(1+v)` is exactly MODE B's
denominator `D`. MODE B computes `N = C / D` (division — D must be checked for ≤ 0, because
dividing by a non-positive number is either undefined or sign-flipping). MODE C computes
`ADC = N·D − F` (**multiplication**, not division) — `D` here is just a coefficient, and no
value of `D` (including zero or negative) makes the computation undefined. **This is why MODE C
has no denominator-based ERROR case the way MODE B's `denominator ≤ 0` does** — see §8.

**Self-check (independent of the inversion above, per the MODE B lesson — see §7):**

```
CM  = N − ADC − F − bN − aG
CMR = CM / N
```

`CMR` must equal `t` exactly when `ADC` is `OK`. This is computed via the actual cost identity
(`N − ADC − F − bN − aG`), **not** `t × N` — `t × N` would just restore the target used to solve
for `ADC` in the first place and cannot catch an arithmetic error in the derivation (this is the
exact mistake MODE B's Excel layer made and was corrected for — see
`docs/features/mode_b_target_price/SPEC.md` and `core/engine/common.py`'s docstring history).

## 4. Market price normalization

**Uses `common.resolve_price_basis()` as-is — no new logic.** `target_market_price` (§1a,
currency-converted via `common.convert_to_reporting()` using that same component's `currency`)
plus that component's own `price_includes_vat` and `tax.vat_rate` resolve to `(N, G)` exactly
the way MODE A's `actual_price_ex_vat`/`gross_payment_incl_vat` resolve `actual_price` — same
function, different field passed in as `price`:

```
price_includes_vat = true   ->  G = price ;  N = price / (1+v)   [N needs v]
price_includes_vat = false  ->  N = price ;  G = price × (1+v)   [G needs v]
price_includes_vat = null   ->  N and G both UNKNOWN
```

## 5. F / b / a aggregation

Restricted to `cost_category = variable_selling_delivery` only (never
`product_service_direct_cost`, never `fixed_operating_cost` — Contribution Margin excludes fixed
operating cost in every mode of this Harness, dependency_rules.md §3):

- **F** — sum of amount-valued items (money, not rate).
- **b** — sum of `rate` values where `basis = rate_of_net_sales`.
- **a** — sum of `rate` values where `basis = rate_of_gross_payment`.

**No-item vs. null — same rule as MODE A/B, stated explicitly because it is easy to blur in
prose (and an earlier draft of this document did):**

| Situation | Result | Why |
|---|---|---|
| **No** `variable_selling_delivery` item at all matches this component/basis | `F`/`b`/`a` = **confirmed `0`**, status `OK` | Nothing to sum is not missing data — there is no cost of that kind. `null != 0` cuts the other way here too: absence of a matching *item* is not the same question as a *field on an item* being null. |
| A matching item **exists**, but its required `amount` (for F) or `rate` (for b/a) is `null` | `F`/`b`/`a` = **UNKNOWN** | The item is known to exist and apply, but its value has not been entered yet — this is the missing-data case. |
| A matching item **exists** with `amount`/`rate` explicitly `0` | Included as `0` in the sum, status `OK` | An explicit, confirmed zero is a real value, not a missing one (`null != 0`). |

These three rows are mutually exclusive and must never be collapsed into one blanket phrase like
"필요한 variable cost/rate 없음 → UNKNOWN" — that phrasing conflates "no item" (row 1, `OK`)
with "item present but its value is null" (row 2, `UNKNOWN`), which are different situations
with different statuses. §13's UNKNOWN list and CASE.md's TC17/TC18 (added below) exist
specifically to keep this distinction explicit.

`applies_to_component = "shared"` items are included subject to the canonical shared-cost rule
(§10). No cost-aggregation helper is shared from `common.py` (none exists — see its docstring);
MODE C implements its own aggregation functions locally, the same way MODE B does not reuse
MODE A's `_sum_cost_category`.

## 6. VAT dependency — per metric, never blanket

Directly from §3's derivation: `v` only ever enters through the `a(1+v)` term. Per metric:

| Metric | `v` required when |
|---|---|
| `market_net_sales_ex_vat` (N) | `price_includes_vat = true` (regardless of `a`) |
| `market_gross_payment_incl_vat` (G) | `price_includes_vat = false` (regardless of `a`) — always required to compute G itself when the display basis isn't G |
| `allowable_direct_cost` (ADC) | needs `N` always (inherits N's rule above) **and** needs `G` only if `a > 0` (inherits G's rule above, but only when `a` makes the `aG` term non-zero) |
| `expected_contribution_margin` / `_rate` | mirrors ADC's dependency (same inputs) |

**Concretely, per the review's explicit test case**: `price_includes_vat = false` (N is the raw
price, immediate, no `v` needed for N itself) **and** `a = 0` (the `aG` term vanishes) **and**
`vat_rate = null` → `ADC` is still **OK** — `v` is never touched by the computation. Change only
`a` to a positive rate with `v` still `null` → `ADC` becomes **UNKNOWN** (needs `G`, which needs
`v`), with **everything else held constant**. This is the exact TC11-vs-TC12 distinction from
MODE B's SPEC, carried over unchanged — the same principle, not a new one.

## 7. Target CM rate validation

Same three-way rule as MODE B:

```
target_contribution_margin_rate = null        ->  UNKNOWN
0 <= t < 1                                     ->  OK
t < 0  or  t >= 1                              ->  ERROR
```

`t = 0` is a valid explicit zero (target: break even at the margin level exactly) —
`null != 0` applies here exactly as everywhere else in this Harness.

## 8. Negative `allowable_direct_cost` — design decision

**`ADC < 0` is `OK`, not `ERROR`, and the value is never clamped to 0.**

Rationale: unlike MODE B's `N = C / D`, MODE C's `ADC = N·D − F` involves no division — every
combination of known, valid `N`, `t`, `b`, `a`, `v`, `F` produces a single well-defined real
number, including a negative one. A negative `ADC` is not a calculation failure; it is a
**valid, confirmed answer**: "given this market price, this fee structure, and this target
margin, there is no amount of direct cost — not even zero — that reaches the target." That is
economically important information a consultant needs to see as a number (and how far negative
it is), not a fact hidden behind a generic ERROR.

Distinguishing this from MODE B's `denominator ≤ 0` ERROR is intentional and follows directly
from §3's derivation, not from a stylistic preference — MODE B's case is a genuine mathematical
non-computability (division by a non-positive number); MODE C's case is a fully computable,
merely unwelcome, result.

**Treatment**: `allowable_direct_cost` metric stays `status = OK` with its (possibly negative)
`value`. A **non-blocking** warning is attached — `severity: "warning"` (not `"blocking"`),
`code: "NEGATIVE_ALLOWABLE_COST"` — stating that the target margin is not achievable at any
direct cost given the current price/fee structure. Downstream metrics
(`expected_contribution_margin`, `expected_contribution_margin_rate`) compute normally from this
negative `ADC` and the self-check (§3) still holds by construction (`CMR = t` exactly, even
though the underlying number is uneconomic).

Open item for implementation time (not decided here): whether a dedicated boolean/enum
"feasibility" field earns its place as a real output metric in a later version, once real usage
shows whether consultants need to filter/sort by it beyond reading the warning. **Not added in
v0.1** — see §12.

## 9. `actual_direct_cost` and `direct_cost_gap` — included in v0.1

Two additional metrics, computed from `cost_category = product_service_direct_cost` items
(the same aggregation MODE A's `direct_cost_total` performs, reused conceptually — not
code-shared, per §5's note):

```
actual_direct_cost  = sum of product_service_direct_cost items assigned to this component
direct_cost_gap     = allowable_direct_cost − actual_direct_cost
```

**Decision: included.** The gap is cheap to compute (the aggregation already exists in the same
shape as MODE A's), and it is the single number that turns "here is an abstract allowable
budget" into "here is whether your current product already fits inside it" — directly
actionable for a consultant, and the reason MODE C's `actual_direct_cost` must **never** be
subtracted into the `ADC` formula itself (§5's explicit warning) — the two are structurally
independent metrics compared only at the end, never merged upstream.

```
gap > 0   ->  current direct cost has room (actual cost is below the allowable ceiling)
gap = 0   ->  current direct cost exactly at the ceiling
gap < 0   ->  current direct cost exceeds what the target margin can afford
```

If `actual_direct_cost` is UNKNOWN (no direct-cost items entered, or one has neither
`amount` nor `rate`... though direct cost items are always amount-valued in this Harness's
existing convention, per MODE A), `direct_cost_gap` is UNKNOWN too — but see the dependency
isolation rule immediately below for what this does, and crucially does **not**, propagate to.

### Dependency isolation — `allowable_direct_cost` never depends on `actual_direct_cost`

`allowable_direct_cost` (ADC) is computed from `{N, G (only if a>0), t, F, b, a}` alone (§3, §6).
`product_service_direct_cost` items are **never read** while computing ADC — not summed into it,
not checked for presence, nothing. This means a problem on the *actual* direct-cost side must
never leak into ADC's status, and a problem on the *variable-cost* side must never leak into
`actual_direct_cost`'s status. Stated as three cases (the ones a real Client Input will actually
produce):

| Case | Condition | `allowable_direct_cost` | `actual_direct_cost` | `direct_cost_gap` |
|---|---|---|---|---|
| **A** | N/G/t/F/b/a all resolvable; no `product_service_direct_cost` item entered, or one exists with `amount = null` | **OK** | UNKNOWN | UNKNOWN |
| **B** | Same as A, but the missing/unresolved piece is specifically a **shared `product_service_direct_cost`** item with an unresolved `allocation_rule` (`by_component_revenue`/`fixed_share`/missing) | **OK** (unaffected — ADC never reads direct-cost items, shared or not) | UNKNOWN, code `UNSUPPORTED_SHARED_COST_ALLOCATION` | UNKNOWN |
| **C** | A **shared `variable_selling_delivery`** item (feeding F, b, or a) has an unresolved `allocation_rule` | UNKNOWN (or ERROR, if the unresolved item is `shared`+`direct` — §10), because F/b/a itself is now UNKNOWN/ERROR | Unaffected — direct-cost items were never touched | Same status as `allowable_direct_cost` (inherits it, since ADC is now not-OK) |

The rule in one sentence: **a problem finding/resolving `product_service_direct_cost` items
can UNKNOWN `actual_direct_cost` and `direct_cost_gap`, but must never UNKNOWN or ERROR
`allowable_direct_cost` — and symmetrically, a problem in F/b/a's inputs must never touch
`actual_direct_cost` on its own** (though it will still show up in `direct_cost_gap`, purely
because the gap's own formula needs both sides). This is not a new principle — it follows
directly from §3's derivation never mentioning `actual_direct_cost` at all — but it is stated
explicitly here because the two aggregations (`variable_selling_delivery` vs.
`product_service_direct_cost`) are easy to accidentally conflate when implementing MODE C's
aggregation functions (§5), given how similar their shape is to each other.

## 10. Shared-cost allocation — canonical rule, unchanged

Applies identically to F/b/a and to `actual_direct_cost`, with **no new semantics**:

| `allocation_rule` on a `"shared"` item | Result |
|---|---|
| `blended_only` | Excluded at component level (by design) |
| `by_component_revenue` / `fixed_share` / missing / unrecognized | **UNKNOWN** — `UNSUPPORTED_SHARED_COST_ALLOCATION`, dependency `blended.allocation[<item_id>]` (or `costs.items[<item_id>].allocation_rule` for missing/unrecognized) |
| `direct` | **ERROR** — `INVALID_ALLOCATION_CONFIGURATION`, dependency `costs.items[<item_id>].allocation_rule` — `"shared"` and `"direct"` remain a semantic contradiction in every mode (`dependency_rules.md` §4) |

## 11. Multi-component and discount — limitations carried forward, not resolved here

- **`target_contribution_margin_rate` stays global**, applied identically to every
  `price_component`, exactly as MODE B currently does. Per-component target rates are not
  implemented in this step — same limitation, not newly introduced.
- **`discount_rate` is out of scope for MODE C v0.1.** MODE B's discount inversion
  (`selling_price -> list_price`) answers a different question ("what should the price tag
  say") that MODE C's market-price-as-given framing does not need. If a future case requires
  reconciling a market *list* price against a *net* transacted price, that is a MODE C v0.2
  addendum, not resolved here.
- Multi-component pooling for module status uses `common.aggregate_module_status()` exactly as
  MODE A/B do — verified order-independent, ERROR-outranks-UNKNOWN (see MODE A/B's own
  regression tests for the pattern MODE C's tests, when written, must replicate).

## 12. Output metrics (v0.1 candidate set)

All wrapped `{value, status, unit}` per `analysis_result.schema.json`'s existing `metric`
definition — no schema change needed, same shape MODE A/B already use.

| Metric | Formula | Status notes |
|---|---|---|
| `market_net_sales_ex_vat` | N, via `resolve_price_basis` | UNKNOWN if price/price_includes_vat/vat_rate missing per §6 |
| `market_gross_payment_incl_vat` | G, via `resolve_price_basis` | UNKNOWN if price_includes_vat=false and vat_rate missing |
| `allowable_direct_cost` | `N[1−t−b−a(1+v)] − F` | OK even when negative (§8); UNKNOWN if N/F/b/a/t (or v, when a>0) missing; ERROR if t invalid or shared+direct |
| `actual_direct_cost` | sum of `product_service_direct_cost` items | Same rules as MODE A's `direct_cost_total` |
| `direct_cost_gap` | `allowable_direct_cost − actual_direct_cost` | UNKNOWN if either input is; never independently ERROR |
| `expected_contribution_margin` | `N − ADC − F − bN − aG` (self-check identity, §3) | Mirrors ADC's status |
| `expected_contribution_margin_rate` | `expected_contribution_margin / N` | Should equal `t` exactly when OK |

**No `denominator` metric is exposed** (unlike MODE B) — see §3's note: MODE C's bracketed term
never independently gates a status the way MODE B's division-based denominator does, so
exposing it as a separate output would not carry the same diagnostic meaning and was judged not
worth the extra surface area for v0.1.

Module-level `status` via `common.aggregate_module_status()` — canonical 3-tier
(OK / INCOMPLETE / ERROR), identical rule to MODE A/B.

## 13. UNKNOWN / ERROR — summary

**UNKNOWN** (missing input, not a calculation failure):
- Market selling price missing (`target_market_price = null`, §1a)
- `price_includes_vat = null`
- Required `vat_rate` missing (per §6's per-metric table — never blanket)
- `target_contribution_margin_rate = null`
- A `variable_selling_delivery` item that **matches** F/b/a's category+basis **exists but has
  `amount`/`rate = null`** (§5's no-item-vs-null table, row 2). **Not** the same as "no matching
  item exists" — that case is a confirmed `0`, `OK` (§5, row 1), not UNKNOWN.
- No `product_service_direct_cost` item entered, or one exists with `amount = null` →
  `actual_direct_cost` (and therefore `direct_cost_gap`) UNKNOWN — **never**
  `allowable_direct_cost` (§9's dependency-isolation table, Case A/B)
- Unresolved shared-cost allocation (`by_component_revenue` / `fixed_share` / missing rule) —
  affects whichever aggregate (F/b/a, or `actual_direct_cost`) the shared item feeds; see §9's
  Case B vs. Case C for which downstream metrics that does and does not touch
- `fx.rate_base_per_reporting` missing for a cross-currency item

**ERROR** (data present, computation still invalid or confirmed-contradictory):
- `target_contribution_margin_rate < 0` or `>= 1`
- `applies_to_component = "shared"` + `allocation_rule = "direct"` (`INVALID_ALLOCATION_CONFIGURATION`)
- Unsupported currency conversion (`convert_to_reporting`'s existing ERROR case)
- A negative `b`/`a` rate or negative `F` amount entered (defensive input-validity check, same
  discipline as MODE B's denominator-input guards)

**Explicitly NOT an ERROR** (§8): `allowable_direct_cost < 0` on otherwise valid, fully-known
inputs. This is the one place MODE C's ERROR surface is *smaller* than MODE B's, and that
difference is derived from the algebra (§3), not asserted by convention.

## Explicitly out of scope for this draft

- No code (`core/engine/modes/mode_c.py` not started)
- No schema changes applied yet — §1a/§1b's `price_components[].target_market_price` field is a
  recommendation for implementation time, not something this document modifies
- No tests
- No Excel MODE C
- `discount_rate` handling (§11)
- Per-component target CM rate (§11)
- Generalized cost-aggregation refactor (§5's note — still per-mode local aggregation)
- BEP, blended economics, Scenario Compare, Dashboard, AI Pricing Strategy — untouched
- A dedicated "feasibility" output field beyond the `NEGATIVE_ALLOWABLE_COST` warning (§8, open item)
