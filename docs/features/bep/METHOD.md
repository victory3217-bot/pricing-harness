# BEP (Break-Even Point) — METHOD (DRAFT v0.1)

```
Methodology source status:
- Pricing Harness Internal Specification: ACTIVE (design draft, not yet coded)
- Master Note derived methodology reference: ACTIVE (via MASTER_NOTE_PRICING_REFERENCE.md)
- Direct Master Note source access in this repository: NOT AVAILABLE
- External academic/reference validation: PENDING
```

This repository does not hold the Startup Master Note original. Every claim below attributed to
the Master Note is sourced only through
[`docs/reference/MASTER_NOTE_PRICING_REFERENCE.md`](../../reference/MASTER_NOTE_PRICING_REFERENCE.md)
and its cross-references — never quoted or paraphrased as if from the original text.

## Business Purpose

MODE A tells a client what today's price is actually earning per unit. That number alone doesn't
answer a question every business eventually has to answer: *does this actually work as a
business?* A positive Contribution Margin per unit is necessary but not sufficient — if fixed
operating costs are large enough relative to that margin, the business can sell every unit at a
"profitable" per-unit margin and still lose money overall, because it never sells enough units to
clear the fixed cost floor. **BEP answers: at today's price and cost structure, how many units
would have to be sold before fixed operating cost is fully recovered?**

Business question:

> "현재 가격과 Contribution Margin 구조에서 고정운영비를 회수하려면 몇 단위를 판매해야 하는가?"

## Master Note Supported Concept

> Source: `MASTER_NOTE_MAPPING.md` §9 (BEP / Feasibility — MN07 Primary, MN06 Secondary) and
> `MASTER_NOTE_PRICING_REFERENCE.md` §8.1/§8.2 (MN06→MN07 입력, "비즈니스모델은 정성에서
> 정량으로 넘어가야 한다")

Ideas the Reference attributes to the Master Note that BEP operationalizes (paraphrased from the
Reference, not the original text):

1. MN06에서 MN07로 넘어가는 핵심 입력은 가격, 비용·마진 구조, 수익모델 세 가지다 — BEP's two
   inputs (current price's CM structure, from MODE A's semantics; fixed operating cost, from the
   same `client_input`) are exactly the first two of these three. BEP is the first module that
   actually *uses* the third (a quantity/revenue-model dimension), even though only in the
   minimal "how many units" sense — a fuller revenue-model treatment (B2C/B2B/B2G effective
   market sizing) is `MASTER_NOTE_PRICING_REFERENCE.md` §8.3/§8.4 territory, out of scope here.
2. 비즈니스모델은 정성에서 정량으로 넘어가야 하며, 특정 가격·수량에서 매출·비용·잔여이익·실행
   가능성까지 이어져야 한다 — BEP is the quantitative feasibility check this describes, applied
   at a single price point (today's actual price).
3. MN07은 P×Qty로 매출을 표현할 수 있지만 Qty의 정의는 거래관계·사업구조에 따라 달라진다 — this
   is the Master Note's own acknowledgment that "quantity" is not a single universal concept
   across business models; it directly motivates SPEC.md §8's decision to exclude any
   `type`-inferred rounded-quantity metric from v0.1 entirely (rather than guessing quantity
   discreteness from `price_components[].type`), and SPEC.md §4's refusal to assume a specific
   analysis period without schema evidence.

## Internal Specification Needed (Master Note does NOT define this)

Per `MASTER_NOTE_MAPPING.md` §9, explicitly: **"BEP 계산식(고정비÷Contribution Margin 단가 등
구체 공식) — Reference에 표준 공식 없음."** Everything below this line — the exact formula, every
UNKNOWN/ERROR/warning rule, the shared-cost `blended_only` deviation (SPEC.md §12), the
single-component restriction (SPEC.md §11) — is Pricing Harness Internal Specification, not a
Master Note derivation. This document must never be read as "the Master Note says BEP =
FC/CMu" — it does not say that, or anything numerically specific about BEP at all.

## Design comparison: where does BEP get its Contribution Margin per unit?

SPEC.md §3 states the decision (Design 2). This section carries the actual comparison.

### Design 1 — BEP consumes `analysis_result.mode_a`

BEP's entry point would be `run_bep(client_input, mode_a_result)` (or read
`mode_a_result["per_component"][cid]["contribution_margin"]` directly), reusing MODE A's
already-computed metric object instead of recomputing anything.

**Pros:**
- Zero formula duplication — BEP literally cannot drift from MODE A's CM number, because it's
  the same object.
- Cheap: no re-walking `costs.items[]`.
- If MODE A's CM calculation logic ever changes, BEP automatically picks up the change with no
  BEP-side code touch.

**Cons:**
- Couples BEP's function signature to MODE A's output shape — `run_bep` would need either a
  pre-computed `mode_a_result` argument (awkward: every caller must remember to run MODE A first
  and thread the result through) or would need to call `run_mode_a(client_input)` itself
  internally (a hidden cross-module dependency: BEP silently becomes "MODE A + something,"
  which is a bigger conceptual coupling than "BEP reads client_input like every other mode
  does").
- Breaks the uniform `run_x(client_input) -> result` signature every other mode
  (`run_mode_a`/`run_mode_b`/`run_mode_c`) currently has. `result_builder.py` calls all three
  modes independently and in any order; a BEP that depends on MODE A's *result object* (not just
  its *semantics*) would force an ordering dependency into `result_builder.py` that doesn't
  exist today.
- Directly blocks SPEC.md §1's stated future direction: a Scenario Compare module that runs BEP
  against MODE B's `required_selling_price` or MODE C's `target_market_price` instead of the
  current price would need a *different* CM number than MODE A's (computed at a different price)
  — if BEP's only way to get CM is "read MODE A's result," Scenario Compare would have to
  fabricate a fake MODE A result object just to feed BEP, or BEP would need two totally different
  code paths (one reading MODE A, one computing fresh) depending on which price it's evaluating.

### Design 2 — BEP independently recomputes CM per unit from `client_input`, via a shared
    primitive module (CHOSEN, IMPLEMENTED)

BEP's entry point is `run_bep(client_input)`, identical in shape to `run_mode_a/b/c`. Internally
it re-walks `costs.items[]` for the analyzed component using the *same aggregation rules* MODE A
uses (same cost-category filters, same shared-cost classification, same VAT-dependency logic via
`common.resolve_price_basis()`), landing on its own `contribution_margin_per_unit` metric — by
calling the same `core/engine/economics.py` primitives (`price_converted`, `sum_cost_category`)
MODE A itself calls, not by re-implementing that logic a second time and not by importing
`mode_a.py`.

**Pros:**
- Uniform signature with every other mode — `result_builder.py` can call `run_bep(client_input)`
  independently of MODE A, in any order, exactly like it already calls MODE B/C independently of
  MODE A.
- Directly composable with the future Scenario Compare direction (SPEC.md §1): the same shared
  primitives, if pointed at a different price value, can serve a future BEP-against-MODE-B/C-price
  variant without needing a MODE A result object to exist for that alternate price at all.
- No hidden cross-module dependency or call-ordering requirement, and — once implemented — no
  BEP→MODE A dependency of any kind (BEP imports only `core/engine/economics.py` and
  `core/engine/common.py`, never `core/engine/modes/mode_a.py`).

**Originally-anticipated con, now resolved by implementation:** the first draft of this
comparison expected "formula duplication with `mode_a.py`'s cost-aggregation helpers... until/
unless a shared helper is factored into `common.py`," deferred as a KEEP LOCAL item. That
deferral did not survive the implementation review: a code-level contamination audit found BEP's
first implementation importing `mode_a.py`'s private (underscore-prefixed) helpers directly —
architecturally backwards (a sibling module reaching into another sibling's private internals,
rather than both depending on a shared layer). The fix was `core/engine/economics.py`: a small,
new module holding exactly `price_converted`/`sum_cost_category`/`DIRECT`/`VARIABLE` — the two
primitives MODE A and BEP actually compute identically — with MODE A itself migrated onto it (no
duplicate implementation left in `mode_a.py`). This landed inside BEP v0.1's own implementation
phase, not deferred to "once BEP and Scenario Compare both need this" as originally planned; the
trigger turned out to be BEP alone, once the private-helper coupling made the need for a proper
shared layer immediate rather than hypothetical. `economics.py` deliberately stayed narrower than
"generalize every mode's cost logic" (SPEC.md §12) — MODE B's flat C/b/a, MODE C's F/b/a-with-
isolation, and BEP's own `fixed_operating_cost` aggregation (with its `blended_only` deviation)
all remain local to their own modules, unmigrated, by design.

Remaining real cost: still some per-call recomputation (BEP re-walks the same cost items MODE A
already walked for the same Client Input) — not material at this scale, the same order of
magnitude as MODE B/C already re-deriving N/G instead of reading MODE A's.

**Decision: Design 2, with the shared `economics.py` extraction done as part of BEP v0.1 itself.**
The signature-uniformity and Scenario-Compare-composability arguments were the deciding factors;
the extraction that was originally expected to wait turned out to be necessary immediately, once
the alternative (private-helper reuse) was identified as an architecture violation rather than an
acceptable interim shortcut.

## Calculation walkthrough (v0.1, single component)

1. **Gate first, before touching any per-component logic**: if `product.price_components[]` has
   more than one entry, return immediately with `status="ERROR"`, `per_component={}`, and the
   single `MULTI_COMPONENT_BEP_NOT_SUPPORTED` warning (SPEC.md §11, finalized). No metric is
   computed for any component in this case.
2. Compute `(N, G)` for the component via `common.resolve_price_basis()`, keyed to `actual_price`
   — identical call MODE A already makes. (BEP's price source is explicitly `actual_price`, never
   `target_market_price`/`required_selling_price` — SPEC.md §1.)
3. Aggregate `product_service_direct_cost` + `variable_selling_delivery` items for this component
   using MODE A's existing per-category/per-basis rules (rate-of-net-sales → ×N, rate-of-gross-
   payment → ×G, fixed-amount → summed directly; shared items classified per the canonical rule,
   `dependency_rules.md` §4, unchanged for these two categories).
4. `contribution_margin_per_unit = N − direct_cost − variable_cost_total`, status/dependencies
   following the same OR-of-ERROR/UNKNOWN-over-dependencies pattern as every other mode's
   metrics. This metric is always OK/UNKNOWN/ERROR — never `NOT_APPLICABLE` (SPEC.md §6).
5. Aggregate `fixed_operating_cost` items for this component per SPEC.md §4/§7/§12 (component-
   scoped items counted directly and checked for `amount < 0` → ERROR per §4's new rule; shared
   items classified per the canonical rule **with the `blended_only` → UNKNOWN deviation**;
   basis-consistency check across contributing items).
6. Compute `break_even_quantity_exact` per SPEC.md §5/§6/§9's priority: ERROR beats UNKNOWN beats
   the FC×CMu-sign matrix (§9 — which decides between a plain division, `0`, or `NOT_APPLICABLE`)
   beats the plain division. `break_even_quantity_units` is not computed at all (§8, excluded).
7. Module status via `aggregate_module_status()` over the 2-3 metrics above (`contribution_margin_
   per_unit`, `fixed_operating_cost`, `break_even_quantity_exact`), unchanged canonical rule —
   confirmed (SPEC.md §15) to already treat `NOT_APPLICABLE` as inert with zero code changes.

## Open items carried forward to implementation time

See SPEC.md §18 for the authoritative, current list — as of this revision, only two items remain
open: revenue-side `type` vs. fixed-cost `basis` period cross-validation, and whether the schema
should eventually gain explicit analysis-period metadata. Everything else raised during this
design's review (multi-component refusal mechanism, the Contribution Margin economic primitive
extraction into `core/engine/economics.py`, negative-fixed-cost-amount handling, CM≤0 semantics,
etc.) has a closed, implemented decision — SPEC.md §18's "Explicitly closed" list is the
authoritative pointer into each section. This METHOD.md does not itself resolve the two remaining
open items — they stay open design gaps until a future phase revisits them with a concrete need.
