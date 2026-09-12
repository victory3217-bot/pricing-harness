# Scenario Compare — METHOD (DRAFT v0.1)

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

MODE A/B/C and BEP each answer one precise question at one fixed set of assumptions: what is
this price earning, what price is needed, what cost is affordable, how many units to break even.
A real pricing decision is rarely made from a single answer to one of those questions — it comes
from comparing several plausible assumption sets side by side: *what if we raised price 10%? What
if we cut a supplier cost? What if the market won't bear more than X?* Doing that comparison by
hand means re-running each mode manually against a slightly different Client Input and
eyeballing the differences. **Scenario Compare is the layer that makes that comparison a first-
class, repeatable operation** — not a new calculation, but a disciplined way to run the existing
calculations several times with controlled, visible differences and line the results up.

Business question:

> "가격·원가·목표 수익성·고정비 조건을 다르게 가정했을 때, 각 시나리오의 경제성이 어떻게
> 달라지는가?"

## Master Note Supported Concept

> Source: `MASTER_NOTE_MAPPING.md`'s BEP/Feasibility and Validation/Feedback rows (MN07 primary
> for feasibility-at-a-price-and-quantity; MN08 for revisiting assumptions against outcomes), and
> `MASTER_NOTE_PRICING_REFERENCE.md`'s general framing that pricing decisions require moving from
> qualitative to quantitative and then checking the numbers against reality.

Ideas the Reference attributes to the Master Note that Scenario Compare is a natural extension
of (paraphrased from the Reference, not the original text):

1. MN07의 feasibility 점검(특정 가격·수량에서 사업이 성립하는가)은 원래 하나의 가정에 대한
   점검으로 그려지지만, 실무에서 경영진은 항상 "이 가정이 아니라면 어떨까"를 묻는다— Scenario
   Compare는 같은 feasibility 점검을 여러 가정에 대해 나란히 반복하는 것일 뿐, 새로운 점검
   기준을 만들지 않는다.
2. MN08의 정신(실제 데이터가 나타나면 가설을 재검토한다)은 Scenario Compare가 다루는 "사전
   대안 비교"와는 엄밀히 다르다 — MN08은 시장 피드백 이후의 재검토이고, Scenario Compare는
   실행 이전의 가정 비교다. 이 구분을 문서에서 흐리지 않는다: Scenario Compare를 "Validation"
   기능으로 서술하지 않는다.

## Internal Specification Needed (Master Note does NOT define this)

The Master Note does not define, and no Reference section claims it defines: a base+override
data model, JSON-level merge semantics, a scenario-level status rollup rule, delta-metric
definitions, or a baseline-selection convention. All of SPEC.md's substantive decisions are
Pricing Harness Internal Specification — the Master Note motivates *why compare scenarios at
all*, not *how*.

## Design comparison: snapshot vs. base+override (SPEC.md §2)

### Design A — full Client Input snapshot per scenario

Each scenario is simply its own complete `client_input`. Comparison happens by running all four
modes over each independently and placing results side by side.

**Pros:**
- Zero new data model — every scenario is exactly what every mode already accepts.
- No merge semantics to design or get wrong.

**Cons:**
- N scenarios means N full documents, most of whose fields are identical to each other by
  intent (only 1-2 fields were meant to differ) — the *actual* difference between scenarios has
  to be reconstructed by diffing two large JSON documents, which is exactly the manual comparison
  Scenario Compare exists to remove.
- No structural guarantee that "unrelated" fields actually stayed unrelated — a typo made while
  hand-copying scenario B from scenario A (a stray currency change, a forgotten cost item) can
  silently make the comparison meaningless, with no mechanism to catch it.
- Awkward for the future Excel/UI direction: a UI built around "these are the 3 things that
  changed" is far more natural than one built around "here are 5 full documents."

### Design B — base + explicit overrides (CHOSEN)

One `base_input`; each scenario carries a short, grouped set of overrides (SPEC.md §4's
`components`/`cost_items`/`targets`/`tax`/`fx` shape, addressed by `component_id`/`item_id` —
not a flat path string) applied to a deep copy of it.

**Pros:**
- The override list *is* the human-readable statement of what the scenario assumes differently —
  no reconstruction needed.
- Structurally guarantees every non-overridden field is identical across scenarios (a deep copy
  of the same `base_input`), which is exactly the property needed for the comparison to mean what
  it claims to mean.
- Naturally maps to a spreadsheet/UI "base case + adjustments" mental model.

**Cons:**
- Requires designing merge semantics precisely (SPEC.md §5) — get this wrong (e.g. allow
  index-based array overrides) and the tool silently corrupts scenarios instead of comparing them
  correctly. This risk is real, not hypothetical, which is why SPEC.md §4/§6 spend real space on
  it rather than waving it away.
- A scenario that actually needs to change many unrelated things (approaching a full rewrite) is
  more awkward to express as a long override list than as a fresh document — judged an acceptable
  trade-off for v0.1, since the primary use case (a handful of assumption changes per scenario)
  is exactly what override lists are good at.

**Decision: Design B**, with the override mechanism deliberately narrow (SPEC.md §3) rather than
a general JSON-patch engine — see the next comparison.

## Design comparison: override mechanism shape (SPEC.md §6)

### Option A — JSON Merge Patch (RFC 7386) style

Overrides expressed as a partial JSON document merged into `base_input` using standard merge-
patch rules.

**Rejected.** RFC 7386's array semantics are "replace the whole array" — there is no standard,
safe way to say "change just this one array element" without replacing the entire
`price_components[]` or `costs.items[]` array, which reintroduces Design A's duplication problem
one level down (the override itself would need to carry the *entire* unchanged array alongside
the one changed value). Any custom array-element-merge convention layered on top of Merge Patch
would just be Option B, dressed up as a generic-sounding standard.

### Option B — explicit, identifier-addressed override list (CHOSEN)

Each override entry names a field using the schema's own stable identifiers (`component_id`,
`item_id` — SPEC.md §3/§6) rather than array indices or generic JSON Pointer array syntax — the
finalized canonical shape (SPEC.md §4) groups overrides by target kind
(`components`/`cost_items`/`targets`/`tax`/`fx`) rather than using a flat path string at all, so
there is no path-parsing ambiguity to begin with. This is a small, closed allowlist (SPEC.md §4)
rather than an arbitrary path grammar — a deliberate constraint, not an oversight: a generic "any
path in the schema"
override mechanism would let a scenario reach into fields whose override wouldn't make sense
(e.g. overriding `schema_version`, or `costs.items[id].cost_category` — which would silently
redefine what a cost item *means*, exactly the kind of new business rule SPEC.md §1 forbids).

**Decision: Option B.** The allowlist can grow later (SPEC.md §22 item 3) if a concrete need
arises; starting narrow and explicit is safer than starting generic and having to retroactively
discover which paths should never have been overridable.

## Calculation walkthrough (v0.1, REVISED — matches SPEC.md §7's finalized 6-step order)

1. **STEP 1 (request-level preflight, SPEC.md §7/§15)**: scenario count ≥ 2 (§16); no duplicate
   `scenario_id`; `baseline_scenario_id` present and matching a real scenario (§13); `base_input`
   has no duplicate `component_id`/`item_id` (§3 — checked against the schema, not guaranteed by
   it); every override's `component_id`/`item_id` exists in `base_input` with no duplicate target
   within one scenario's own override list; every override uses only allowlisted fields (§4). Any
   failure here aborts the ENTIRE request — no scenario is built, no mode engine runs at all.
2. **STEP 2 (merge, SPEC.md §5)**: for each scenario, deep-copy `base_input` and apply its
   overrides — pure field replacement (omitted = keep base value, explicit `null` = UNKNOWN),
   never array-index addressing.
3. **STEP 3 (schema validation, SPEC.md §7/§15)**: validate the merged document against
   `client_input.schema.json`, unchanged. A scenario failing this step becomes
   `scenario_status = ERROR` and runs no mode engine at all for that scenario — but sibling
   scenarios continue independently.
4. **STEP 4 (mode execution, SPEC.md §8)**: for scenarios that passed STEP 3, run
   `run_mode_a`/`run_mode_b`/`run_mode_c`/`run_bep` — always all four, passing through their
   outputs unmodified.
5. **STEP 5 (summary, SPEC.md §9/§10)**: roll up each scenario's overall status from its four
   module statuses, and build the summary view.
6. **STEP 6 (deltas, SPEC.md §14)**: for every non-baseline scenario, compute the delta view
   against the named baseline's own STEP 5 summary, following the `ERROR > UNKNOWN >
   NOT_APPLICABLE > OK` propagation order.

Warnings (SPEC.md §11) are concatenated as part of STEP 4/5 for each scenario — each mode's
warning objects copied verbatim with an added `origin_module` tag, never reinterpreted. The whole
comparison's own top-level status (SPEC.md §19's `scenario_compare_result.status`) is a final
rollup across all scenarios' `scenario_status` values, same `ERROR > INCOMPLETE > OK` priority.

Scenario Compare recomputes nothing at any step — every number is traceable to exactly one
`run_mode_*`/`run_bep` call.

## Open items carried forward to implementation time

See SPEC.md §22 for the authoritative, current list — schema document placement is now closed
(§19, Option B: separate `scenario_compare_request`/`scenario_compare_result` schemas). What
remains open: the Excel scenario-count ceiling, whether structural (not just value-level)
overrides will eventually be needed, whether the delta-metric set should expand to cover MODE C's
allowable-cost metrics, and `break_even_quantity_delta`'s basis-comparability rule should `basis`
ever become overridable. None of these are resolved here.
