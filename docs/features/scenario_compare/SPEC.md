# Scenario Compare — SPEC (DRAFT v0.1)

## 0. Status

Design-only. No Python code, schema change, test, or Excel work exists yet.

## 1. Core question and role — orchestration, not a new engine

**"가격·원가·목표 수익성·고정비 조건을 다르게 가정했을 때, 각 시나리오의 경제성이 어떻게
달라지는가?"**

Scenario Compare is an **orchestration / decision-support layer**, not a fifth calculation
engine. It never defines its own formula for anything MODE A/B/C/BEP already compute. Concretely
forbidden:
- a Scenario-Compare-specific price formula,
- redefining Contribution Margin,
- redefining the BEP formula,
- redefining VAT normalization,
- redefining any cost-allocation rule.

Everything Scenario Compare reports is produced by calling `run_mode_a`/`run_mode_b`/
`run_mode_c`/`run_bep` on a derived `client_input` and passing their results through — it reads
and arranges, it does not calculate. Its purpose is to let a decision-maker compare trade-offs
across assumptions side by side; it does **not** pick a winner (§13).

## 2. What a "scenario" is (Design B — chosen)

Two designs were compared:

- **Design A — full snapshot per scenario**: each scenario carries a complete, independent
  `client_input` document.
- **Design B — base + override**: one `base_input` (a normal, schema-valid `client_input`) plus,
  per scenario, a small, explicit set of field-level overrides.

**Decision: Design B.** Rationale:
- Duplicate data across N scenarios (Design A) makes it hard to see *what actually changed*
  between scenarios — the diff has to be reconstructed by the reader. Design B states the
  difference directly.
- Comparability: two scenarios built from the same base with different overrides are guaranteed
  to agree on everything not explicitly overridden — no risk of an accidental unrelated
  divergence (a typo'd currency, a stale cost item) silently making two "comparable" scenarios
  not actually comparable.
- Future UI/Excel convenience: a base + delta table is a natural spreadsheet/UI shape; five full
  JSON documents are not.

The cost of Design B is that the override mechanism itself needs precise, narrow semantics
(§4-§6) — an unconstrained merge is exactly the risk this SPEC exists to rule out.

**Each scenario, after override application, must itself be a fully valid, ordinary
`client_input`** — indistinguishable, from any mode engine's point of view, from a hand-authored
Client Input. A scenario is never passed to a mode engine "plus scenario context"; it is passed
as a plain `client_input`. This is the enforcement mechanism for §1's "no new semantics" rule: if
the derived document must validate against the unchanged `client_input.schema.json`, Scenario
Compare structurally cannot invent a field or a meaning that schema doesn't already have.

## 3. Stable ID uniqueness — checked against the actual schema, not assumed

`component_id` and `item_id` being `required` fields (confirmed, §6 of the prior revision) is a
different property from their being **unique** within one `client_input`. Checked directly:
`client_input.schema.json` puts no `uniqueItems` constraint on either
`product.price_components` or `costs.items` (grepped for `uniqueItems` in the file — zero
matches), and neither `component_id` nor `item_id` is declared with any cross-item uniqueness
constraint (JSON Schema draft-07, which this file uses, has no built-in way to express
"unique value of a property across array elements" without a custom keyword this file doesn't
define). **Conclusion: a `client_input` with two `price_components[]` entries sharing the same
`component_id`, or two `costs.items[]` entries sharing the same `item_id`, is schema-legal
today.** This is a real gap Scenario Compare must not inherit silently, since its entire
identifier-addressed override mechanism (§5) depends on "this id resolves to exactly one object."

**Preflight rule (new, Scenario-Compare-specific — does not modify `client_input.schema.json`,
does not affect MODE A/B/C/BEP's own validation of a `client_input` they're handed directly):**
- Duplicate `component_id` values within `base_input.product.price_components[]` → request ERROR
  (§8 STEP 1 — checked before any scenario is built).
- Duplicate `item_id` values within `base_input.costs.items[]` → request ERROR (same step).
- These checks run once, against `base_input` only — every scenario is a deep copy of the same
  `base_input`, so a `base_input`-level duplicate would otherwise silently corrupt every
  scenario's overrides identically, not just one.

## 4. Canonical override schema (v0.1)

Overrides are **grouped by target kind**, not a flat `{path, value}` list — this reads closer to
the actual `client_input` shape and makes the allowlist enforceable by structure, not by string-
path parsing. Every field name below is copied verbatim from the current
`client_input.schema.json` (checked, not assumed):

```
overrides:
  components:                          # each entry keyed by component_id (must exist in base_input)
    - component_id: <string, required, must match an existing product.price_components[].component_id>
      actual_price?: <number | null>
      target_market_price?: <number | null>
      price_includes_vat?: <boolean | null>
      discount_rate?: <number | null>

  cost_items:                          # each entry keyed by item_id (must exist in base_input)
    - item_id: <string, required, must match an existing costs.items[].item_id>
      amount?: <number | null>
      rate?: <number | null>

  targets:
    target_contribution_margin_rate?: <number | null>

  tax:
    vat_rate?: <number | null>

  fx:
    rate_base_per_reporting?: <number | null>
```

Every leaf field is optional (`?`) — a `components[]`/`cost_items[]` entry may set only the one
or two fields a scenario actually changes; `component_id`/`item_id` themselves are the only
required fields on their entries (they are the addressing key, not an overridable value — §5
explicitly forbids changing them). `targets`/`tax`/`fx` are singleton groups (the schema itself
has exactly one `targets`/`tax`/`fx` object per `client_input`, no array, no identifier needed).

**Explicitly out of scope for v0.1** (unchanged from the prior revision, restated against the
now-grouped shape):
- Adding or removing a `product.price_components[]` or `costs.items[]` entry — `overrides.
  components[]`/`overrides.cost_items[]` may only reference `component_id`/`item_id` values that
  already exist in `base_input` (§5).
- Changing a cost item's `cost_category`, `basis`, `applies_to_component`, or `allocation_rule` —
  not fields on the `cost_items[]` override entry shape at all (only `amount`/`rate` are).
- Changing a component's or cost item's own `component_id`/`item_id` — these are the addressing
  key, never a value being overridden.
- `discount_schedule` (multi-row policy structure, not a single scalar override).

## 5. Merge semantics (finalized)

Applying `overrides` to a deep copy of `base_input` is a pure, order-independent field
replacement — never a JSON Merge Patch, never array-index addressing:

- **Field omitted from an override entry** → the corresponding `base_input` value is kept
  unchanged (not touched, not nulled).
- **Field explicitly present with value `null`** → that field becomes `null` in the scenario's
  `client_input`, meaning exactly what `null` means everywhere else in this Harness — UNKNOWN,
  per the `null != 0` principle (e.g. `{component_id: "main", actual_price: null}` produces a
  scenario where MODE A's `actual_price_ex_vat` is UNKNOWN, identical to hand-authoring a
  Client Input with that field blank).
- **`overrides.components[].component_id` (or `.cost_items[].item_id`) not found in
  `base_input`** → request ERROR (§8 STEP 1) — never silently ignored, never silently appended
  as a new component/item.
- **The same `component_id` appearing more than once inside `overrides.components[]`** (or the
  same `item_id` more than once inside `overrides.cost_items[]`) → request ERROR (duplicate
  override target) — never resolved by "last one wins."
- **Adding or removing an array entry** (a `component_id`/`item_id` in `base_input` with no
  corresponding override entry is simply left as-is; there is no override shape that could add a
  *new* `component_id`/`item_id` not already in `base_input` — see §4's exclusion list) → v0.1
  unsupported, surfaced as the "not found in base_input" ERROR above if attempted.
- **`cost_category`/`basis`/`applies_to_component`/`allocation_rule` override** → not
  representable in the override schema at all (§4) — a request containing these fields on a
  `cost_items[]` override entry fails schema-level validation of the *override request itself*,
  before `base_input` is even touched.
- **Array-index-based addressing of any kind** → not representable in the override schema (§4's
  grouped-by-id shape has no index-addressed form to begin with).
- **The merged, per-scenario `client_input` must re-validate against the unchanged
  `client_input.schema.json`** (§8 STEP 3) — this is not optional and not a redundant check: an
  override can set a field to a value that's individually schema-legal (e.g. `rate: 1.5`, out of
  `cost_item.rate`'s `[0,1]` bound) only for the *unmodified* schema to correctly reject the
  resulting document, exactly as it would reject a hand-authored Client Input with the same value.

## 6. Cost item identity — a real, not hypothetical, design constraint

This SPEC explicitly checked whether `costs.items[]` has a stable identifier before proposing
item-level overrides: it does (`item_id`, required, `client_input.schema.json` line ~157) — but
per §3, "has an identifier" and "that identifier is unique" are different facts, and only the
first was previously checked. §3's preflight rule closes that gap. Had `item_id` not existed at
all, item-level cost overrides would have been out of v0.1 scope entirely rather than solved with
an invented identifier — Scenario Compare does not get to retroactively assign identity to schema
objects that don't already have it.

## 7. Execution order — six-step pipeline (finalized, authoritative)

Two levels of validation exist and must not be conflated: **request-level** (the whole Scenario
Compare request is malformed — abort before touching any mode engine) and **scenario-level** (one
scenario's overrides don't resolve cleanly — that scenario alone becomes ERROR, siblings still
run). The six steps:

```
STEP 1 — request-level preflight (request ERROR -> STOP, no mode engine ever runs)
  - scenario count >= 2                                                (section 16)
  - scenario_id uniqueness across the request                          (section 15)
  - baseline_scenario_id present                                        (section 13)
  - baseline_scenario_id matches an actual scenario_id in the request   (section 13/15)
  - base_input: no duplicate component_id, no duplicate item_id         (section 3)
  - every overrides.components[].component_id / .cost_items[].item_id
    exists in base_input, with no duplicate target within one scenario's
    own override list                                                   (section 5)
  - every override entry uses only allowlisted fields (section 4)      (schema-level on the
                                                                          override request itself)

STEP 2 — base + override merge (per scenario, pure field replacement, section 5)

STEP 3 — merged client_input schema validation (per scenario, against the
         UNCHANGED client_input.schema.json)
  - fails -> that scenario's status = ERROR; recorded with the schema validation error as the
    scenario's warning; STEP 4 is NOT run for this scenario (no partial/best-effort mode
    execution on an invalid client_input — an invalid document has no well-defined per-mode
    result to report, so none is fabricated); sibling scenarios continue through their own
    STEP 2-6 independently

STEP 4 — run_mode_a / run_mode_b / run_mode_c / run_bep (only for scenarios that passed STEP 3)

STEP 5 — build each scenario's summary view (section 10)

STEP 6 — compute baseline deltas (section 14) for every non-baseline scenario, against the
         baseline scenario's own STEP 5 summary
```

STEP 1's checks are listed in a fixed order only for readability — a request failing multiple
STEP 1 checks simultaneously is reported as a single request ERROR (not a ranked/first-wins
selection among the failures); which specific checks failed should all be surfaced in the
rejection, not just the first one encountered, so the caller can fix every problem in one pass
rather than being told about them one at a time.

## 8. Mode execution strategy — run all four (Design A chosen)

Compared:
- **Design A — always run all four modes** for every scenario.
- **Design B — run only the modes relevant to that scenario's purpose** (e.g. skip BEP for a
  scenario that only varies MODE C inputs).

**Decision: Design A**, for v0.1. Rationale: uniform columns across every scenario (so a
comparison table/dashboard never has to explain "why does scenario C have no BEP row") outweighs
the modest extra compute of running BEP/MODE B on a scenario that doesn't particularly exercise them.
When a scenario's `base_input` (post-override) doesn't have the dependencies a given mode needs,
that mode legitimately reports UNKNOWN/INCOMPLETE — Scenario Compare does not suppress, hide, or
reinterpret that; a scenario built to explore MODE C is expected to show MODE B as
INCOMPLETE/UNKNOWN if no `target_contribution_margin_rate` was ever set, and that is shown
plainly, not treated as a defect (§9 covers the case where a mode's *own* input, not just an
unrelated field, was actually left UNKNOWN or invalid).

## 9. Scenario overall status

Canonical 3-tier rule, kept consistent with `dependency_rules.md` §5 (`ERROR` > `UNKNOWN` >
`OK`/`NOT_APPLICABLE`), applied one level up — over the four **module** statuses instead of over
individual metrics:

- **ERROR**: any of `mode_a.status`/`mode_b.status`/`mode_c.status`/`bep.status` is `ERROR`
  (including BEP's `MULTI_COMPONENT_BEP_NOT_SUPPORTED` gate — §17), OR the scenario failed STEP 3
  (its overrides did not produce a schema-valid `client_input` — §7, no mode engine was run for
  it at all). A STEP-3 failure is reported the same way as a mode ERROR at the scenario-status
  level (both are `scenario_status = ERROR`) even though internally one has real per-module
  statuses and the other has none — the distinction is preserved in the scenario's own warnings
  (§15), not collapsed away, just not given a *different* top-level status tier.
- **INCOMPLETE**: no module is `ERROR`, but at least one module status is `INCOMPLETE`.
- **OK**: every module status is `OK` or `NOT_IMPLEMENTED` (the `blended` block, still
  unimplemented everywhere, is excluded from this rollup entirely — it never participates).

A module reporting `NOT_APPLICABLE`-*shaped* results (e.g. BEP's `break_even_quantity_exact`
being `NOT_APPLICABLE` while `bep.status` itself is still `OK`, per `dependency_rules.md` §7) does
**not** drag scenario status down — this is the same "NOT_APPLICABLE is inert" rule already
established for BEP, simply not re-litigated here: Scenario Compare rolls up *module* statuses,
and a module whose own canonical rule already says "OK despite an internal NOT_APPLICABLE metric"
contributes `OK` to this rollup, full stop.

## 10. Canonical summary metrics (v0.1)

Per scenario, the summary view surfaces (all pulled verbatim from the four mode results, never
recomputed):

```
identity:       scenario_id, label
price:          actual_price (as-run), target_market_price (as-run, if set)
mode_a:         actual_price_ex_vat, gross_payment_incl_vat*, contribution_margin,
                contribution_margin_rate, status
mode_b:         required_selling_price, required_list_price, status
mode_c:         allowable_direct_cost, actual_direct_cost, direct_cost_gap, status
bep:            fixed_operating_cost, contribution_margin_per_unit, break_even_quantity_exact,
                analysis_period_basis, status
overall:        scenario_status (section 9)
```

(`gross_payment_incl_vat` is MODE A's `gross_payment_incl_vat`-equivalent output if present under
whatever name the current schema uses for it per component — included as a reference price
figure, not a new metric.) This list is deliberately the union of what each mode already reports
as its own most-summarizing figures — nothing here is a new calculation, and nothing on this list
is mandatory to *display* (a consuming report/dashboard may show a subset); it is the *maximum*
v0.1 promises to make available per scenario, not a minimum every UI must render.

**Note on `price` (raw `actual_price`)**: shown as-is for reference, but is **not** a delta metric
(§14) — a scenario is allowed to override `price_includes_vat`, so two scenarios' raw
`actual_price` values are not necessarily comparable apples-to-apples (a VAT-inclusive `1100` and
a VAT-exclusive `1000` can represent the identical underlying economics). `mode_a.
actual_price_ex_vat` (already display-convention-normalized by MODE A itself) is the comparable
figure, and is what §14's delta uses.

## 11. Warning aggregation — provenance preserved, never reinterpreted

Each mode's `warnings[]` array is already self-contained (`code`, `severity`, `metric_path`,
`dependency_paths`, `message` — `analysis_result.schema.json`'s existing `warning` definition).
Scenario Compare's aggregation is a **concatenation with an added origin tag**, not a
reinterpretation:

```
scenario_warnings: [
  { origin_module: "mode_a" | "mode_b" | "mode_c" | "bep", ...the original warning object... },
  ...
]
```

`origin_module` is the only new field Scenario Compare adds; every other field is copied
verbatim from the source mode's own warning. Scenario Compare never assigns a new `code`, never
rewrites a `message`, and never infers a cause a mode engine didn't already state — this mirrors
`metric_path`'s existing convention (`mode_a.per_component.*`, `bep.per_component.*` prefixes
already self-identify origin; `origin_module` is redundant with that prefix for convenience, not
a second source of truth that could disagree with it).

## 12. Ranking / recommendation — explicitly excluded

v0.1 does not rank scenarios, does not compute a score, and does not recommend one. This is not a
temporary implementation gap — it is a scope boundary: price decisions depend on market
positioning, customer value perception, competitive dynamics, and strategic intent that this
calculation layer has no access to and no basis for weighing. Scenario Compare's product is a
**descriptive comparison** (numbers placed side by side, differences made visible — §14);
synthesizing those numbers into "the best scenario" is explicitly deferred to a future AI Pricing
Strategy layer (`MASTER_NOTE_MAPPING.md`'s own roadmap already separates these), which can bring
qualitative judgment this layer cannot.

## 13. Baseline scenario — explicit, not positional

**`baseline_scenario_id` is a required, explicit field** on the Scenario Compare request/result —
never inferred from "the first scenario in the list." List order is not identity anywhere else in
this Harness (`price_components[]`/`costs.items[]` order doesn't carry meaning either — §4), and
baseline selection is exactly the kind of thing that becomes a silent bug if it's positional: a
scenario list that gets reordered for display purposes would silently change what every delta is
computed against. `baseline_scenario_id` must name a `scenario_id` that actually exists in the
scenario list (§15's error case for when it doesn't).

## 14. Delta metrics (v0.1 minimum set — REVISED: `price_delta` replaced)

> **Revision note**: the first draft's `price_delta` (`actual_price − baseline.actual_price`) is
> rejected as the canonical delta. `overrides.components[].price_includes_vat` is itself
> overridable (§4) — so `actual_price` on its own can differ between two scenarios purely by
> display convention, with the underlying economics identical (the same case CASE.md's own TC13
> demonstrates: `1100` VAT-inclusive and `1000` VAT-exclusive can be the same `N=1000`). Taking a
> raw difference between two `actual_price` values that might not even share a display
> convention is not a meaningful "how did price change" answer.

Computed only against the named baseline scenario (§13), and only when **both** operands are
themselves numeric:

```
net_sales_ex_vat_delta            (= mode_a.actual_price_ex_vat − baseline's mode_a.actual_price_ex_vat)
contribution_margin_delta         (= mode_a.contribution_margin − baseline's mode_a.contribution_margin)
contribution_margin_rate_delta    (= mode_a.contribution_margin_rate − baseline's mode_a.contribution_margin_rate)
break_even_quantity_delta         (= bep.break_even_quantity_exact − baseline's bep.break_even_quantity_exact)
```

`net_sales_ex_vat_delta` replaces `price_delta`: `mode_a.actual_price_ex_vat` is MODE A's own
display-convention-normalized figure (it is already computed identically regardless of whether
`price_includes_vat` was `true` or `false` on either side — that is precisely what
`resolve_price_basis()` exists to guarantee), so a delta on it is apples-to-apples even when two
scenarios used different display conventions. All four delta metrics are still pulled from
existing mode outputs — no new price calculation is introduced by Scenario Compare itself.

**Delta source module — fixed, never mixed across modes (finalized, closes a gap the prior
revision left implicit):**

| Delta metric | Source (exact field) | Never substitutes |
|---|---|---|
| `net_sales_ex_vat_delta` | `mode_a.per_component[cid].actual_price_ex_vat` | MODE B's `required_net_sales_ex_vat`, MODE C's `market_net_sales_ex_vat` — both exist and are named similarly, but neither is this delta's source |
| `contribution_margin_delta` | `mode_a.per_component[cid].contribution_margin` | BEP's `contribution_margin_per_unit` (same underlying concept, computed via the same `economics.py` primitive as MODE A — but it is BEP's own metric object, not MODE A's, and this delta reads MODE A's) |
| `contribution_margin_rate_delta` | `mode_a.per_component[cid].contribution_margin_rate` | MODE B's/MODE C's `expected_contribution_margin_rate` |
| `break_even_quantity_delta` | `bep.per_component[cid].break_even_quantity_exact` | — (BEP is the only mode producing this metric at all) |

Every delta reads exactly one metric from exactly one mode's already-computed output — Scenario
Compare does not average, reconcile, or choose between two modes' similarly-named metrics for a
single delta value. A future delta metric drawing from MODE B or MODE C (§22 item 3) would be a
**new, separately-named** delta (e.g. a hypothetical `allowable_direct_cost_delta` sourced from
MODE C alone), never a change to what these four existing deltas read.

Not every summary metric gets a delta in v0.1 — this is deliberately the minimum requested, not
an exhaustive delta-of-everything.

**Status propagation (finalized, ordered)**: `ERROR > UNKNOWN > NOT_APPLICABLE > OK`, evaluated
per delta independently:
- either operand `ERROR` → delta `ERROR`;
- else either operand `UNKNOWN` → delta `UNKNOWN`;
- else either operand `NOT_APPLICABLE` → delta `NOT_APPLICABLE` (e.g.
  `break_even_quantity_delta` when either scenario's own `break_even_quantity_exact` is
  `NOT_APPLICABLE` — a delta against "no meaningful break-even quantity" is itself not
  meaningful);
- else (**both operands numeric `OK`**) → delta is computed as a plain numeric subtraction, `OK`.

**Baseline scenario's own delta row (REVISED — no longer an unconditional `0`/`OK`).** The prior
draft claimed the baseline's self-delta is always `0`/`OK` "by definition." **That is rejected as
stated.** A delta being computed *against the same scenario* does not change what the underlying
source metric's own status is — the status-propagation rule (above) applies to the baseline's
self-comparison exactly as it applies to every other scenario's comparison, with both operands
happening to be the same value:

- **Baseline's source metric is numeric, `OK`** → self-delta is `0`, `status: OK` (subtracting a
  number from itself is `0` — the *only* case where the prior draft's claim was actually correct).
- **Baseline's source metric is `UNKNOWN`** → self-delta is `{value: null, status: UNKNOWN}` —
  **not** `0`/`OK`. A scenario cannot claim "zero change" against a number that was never known in
  the first place; `UNKNOWN − UNKNOWN` is not `0`, it is still UNKNOWN.
- **Baseline's source metric is `ERROR`** → self-delta is `{value: null, status: ERROR}`.
- **Baseline's source metric is `NOT_APPLICABLE`** → self-delta is `{value: null, status:
  NOT_APPLICABLE}` (e.g. the baseline scenario itself has `CMu ≤ 0`, so its own
  `break_even_quantity_exact` is `NOT_APPLICABLE` — comparing that against itself is still not a
  meaningful quantity comparison, self-comparison does not manufacture meaning that wasn't there).

This is not a new propagation rule — it is the existing `ERROR > UNKNOWN > NOT_APPLICABLE > OK`
order (above) applied without a special case for "the two operands happen to be identical." The
"self-comparison is definitionally 0" framing is what's rejected, not the propagation rule itself.

## 14a. Invalid baseline scenario (new — closes a gap the prior revision left unaddressed)

`baseline_scenario_id` naming a real `scenario_id` is checked at STEP 1 (§7/§15) — but STEP 1
cannot know whether that scenario will *survive* STEP 3 (its own merged `client_input` might
still fail schema validation, exactly like any other scenario — §7). **Canonical behavior when
the baseline scenario itself fails STEP 3:**

- The baseline scenario's own `scenario_status = ERROR` (§9, unchanged — it is treated like any
  other STEP-3 failure), and its `mode_a`/`mode_b`/`mode_c`/`bep` results are absent (STEP 4 is
  not run for it, same as any scenario that fails STEP 3).
- **Sibling scenarios are NOT aborted.** Every other scenario still runs its own STEP 2-6
  independently — a broken baseline does not cancel the rest of the comparison. Each sibling's
  own **absolute** results (its own `mode_a`/`mode_b`/`mode_c`/`bep` outputs, its own summary) are
  computed and preserved exactly as if the baseline had been valid.
- Every delta metric that requires the baseline's value (all four, §14) becomes
  `{value: null, status: "ERROR"}` for **every** non-baseline scenario — not just for the metrics
  that happened to be involved in whatever made the baseline invalid, since the baseline
  contributes no usable value for *any* delta once it has no mode results at all.
- New warning code, attached at the `scenario_compare_result` level (not invented per-delta):
  `BASELINE_SCENARIO_INVALID_FOR_DELTA`, severity `"blocking"`, referencing the baseline's own
  `scenario_id` and its STEP-3 validation error as `dependency_paths`. This introduces no new
  calculation semantics — it is a descriptive label for "the delta computation's required input
  doesn't exist," using the same warning shape (§11) every other warning already uses.
- Scenario Compare does not fall back to a different baseline, and does not silently treat "no
  usable baseline" as "no deltas requested" — deltas are still listed for every non-baseline
  scenario, each explicitly `ERROR`, so the caller sees *why* no comparison numbers are available
  rather than seeing an empty/absent deltas section that could be mistaken for "nothing to
  compare."

**`break_even_quantity_delta` and `analysis_period_basis` comparability (new, addressing a gap
the prior revision left unstated).** `break_even_quantity_delta` is computed whenever both
operands are numeric `OK`, per the rule above — **without** comparing `analysis_period_basis`
between the two scenarios. This is currently safe by construction: §4's override allowlist has no
path to change a `fixed_operating_cost` item's `basis` (only `amount`/`rate` are overridable on
`cost_items[]`), so every scenario derived from the same `base_input` necessarily shares the same
`analysis_period_basis` as long as none of them hit BEP's own basis-inconsistency/shared-cost
paths (which instead make the metric non-numeric, already excluded by the rule above). **This is
flagged, not silently relied upon**: if a future revision ever allows overriding `basis`
(currently excluded, and not proposed here), `break_even_quantity_delta` would need an explicit
basis-equality check added before subtracting two quantities scoped to different analysis
periods — recorded as an open item (§22).

## 15. Request-level vs. scenario-level errors (finalized split, matches §7's STEP 1 / STEP 3)

**Request-level (STEP 1 — abort the whole comparison, no mode engine runs for anything):**
- Duplicate `scenario_id` across the scenario list — an ambiguous scenario identity makes every
  delta/baseline reference in the request ambiguous, not just the duplicate itself.
- Missing `baseline_scenario_id` — no "assume the first scenario" fallback (§13).
- `baseline_scenario_id` not matching any `scenario_id` in the list.
- Fewer than 2 scenarios (§16).
- `base_input` itself has a duplicate `component_id` or duplicate `item_id` (§3) — this
  corrupts every scenario identically (all are copies of the same `base_input`), so it is a
  request-level defect, not a per-scenario one.
- **Any** scenario's override names a `component_id`/`item_id` that doesn't exist in
  `base_input`, or repeats the same override target twice within one scenario's own override list
  — **finalized as request-level, not scenario-level** (revising the prior draft, which had
  called this scenario-level). Rationale for the change: an unresolvable override target is a
  defect in how the *request itself* was authored (a typo, a stale identifier) — structurally the
  same kind of mistake as a duplicate `scenario_id` or a missing baseline, not a downstream
  calculation failure. Catching it at STEP 1, before any scenario is built, means the caller gets
  every such mistake reported together (§7's "surface every STEP 1 failure, not just the first")
  instead of discovering them one scenario at a time.
- An override entry uses a field outside the allowlist (§4) — a structural defect in the request
  document, checked against the override schema itself before `base_input` is touched at all.

**Scenario-level (STEP 3 — that one scenario's `scenario_status = ERROR`, sibling scenarios still
run their own STEP 2-6 independently):**
- The merged `client_input` (after a *structurally valid* override — passed STEP 1 — has been
  applied) fails validation against `client_input.schema.json` (e.g. an override set
  `cost_items[].rate` to `1.5`, individually out of the `[0,1]` bound `client_input.schema.json`
  already enforces). This is the only remaining scenario-level "bad input" case in v0.1: every
  *identity* problem (unresolvable id, duplicate target) was moved to STEP 1 above, so what's left
  at STEP 3 is purely "the resulting values, once merged, don't satisfy the schema's own value
  constraints" — a case that can only be detected after the merge actually happens, unlike an
  unresolvable identifier, which is detectable by inspecting the override request alone.
- Any of `mode_a.status`/`mode_b.status`/`mode_c.status`/`bep.status` is itself `ERROR` after
  STEP 4 runs (§9) — this is not a new error category, just the existing per-mode ERROR outcome
  surfacing at the scenario level.

## 16. Scenario count

- **Python core**: no hardcoded upper bound. The pipeline (§7) is a per-scenario loop; nothing
  about it stops working past 5. A **lower bound of 2** is enforced (a "comparison" of one
  scenario is not a comparison — this is a request-level validation, same tier as §15's checks).
- **Excel v0.1** (when that phase eventually happens — not this phase, §22): a fixed small
  column budget (5 scenarios, matching the user's own example framing) is the practical
  spreadsheet-layout constraint MODE B/C/BEP's Excel Simulators already accept for their own
  input surfaces. This is explicitly a **presentation-layer limit, not a Python-core limit** —
  the two are allowed to differ, and this SPEC records that difference as intentional rather than
  an oversight to reconcile later.

## 17. Multi-component / BEP interaction — no workaround

Scenario Compare must never paper over BEP's existing single-component restriction
(`dependency_rules.md` §7 / `docs/features/bep/SPEC.md` §11). A scenario whose (post-override)
`client_input` has more than one `price_components[]` entry runs MODE A/B/C over however many
components they can each handle (unchanged mode-level behavior) and gets
`bep.status = "ERROR"` / `MULTI_COMPONENT_BEP_NOT_SUPPORTED` from BEP, exactly as it would outside
Scenario Compare. This is surfaced plainly in that scenario's summary/status (§9's ERROR rollup
already handles this correctly — no special-casing needed) — never collapsed to a single
component to "make BEP work," and never hidden from the comparison view.

## 18. Shared-cost allocation interaction — no workaround

No real shared-cost allocation engine exists yet (`dependency_rules.md` §4/§7, still
`NOT_IMPLEMENTED` everywhere). Scenario Compare does not build one, and does not let an override
target a cost item's `allocation_rule` (§3's exclusion list) — doing so would let a scenario
silently redefine a cost item's shared-cost semantics, which is exactly the kind of new business
rule §1 forbids. Every mode's existing UNKNOWN (`UNSUPPORTED_SHARED_COST_ALLOCATION`,
`FIXED_COST_BLENDED_ONLY_NOT_ALLOCATED`) / ERROR (`INVALID_ALLOCATION_CONFIGURATION`) outcomes for
shared items pass through into the scenario's results and warnings unchanged.

## 19. Schema architecture — finalized: separate document types (Option B)

Two options were compared:

- **Option A — a `scenario_compare` block nested inside the existing
  `analysis_result.schema.json`**, as a new top-level sibling of `mode_a`/`mode_b`/`mode_c`/`bep`.
- **Option B — separate document types**: `scenario_compare_request.schema.json` (the input: a
  `base_input` plus a scenario list with overrides) and `scenario_compare_result.schema.json`
  (the output: per-scenario mode results + summary + deltas + warnings), independent of any
  single `analysis_result` document.

**Decision: Option B.** Rationale:
- `analysis_result.schema.json`'s own description (checked, unchanged) frames the document as
  "Output of the Pricing Engine for **one Client Input**" — every existing top-level block
  (`mode_a`, `mode_b`, `mode_c`, `bep`, `blended`) is a *mode*, computed from that one document's
  data. Scenario Compare is not a fifth mode computed from the same Client Input — it is an
  orchestration layer that runs *N* independently-derived Client Inputs (one per scenario)
  through the existing four modes and arranges the results. Nesting it inside one
  `analysis_result` would misrepresent what the document actually is: an `analysis_result` for
  `base_input` alone, with a `scenario_compare` block bolted on, describes something structurally
  different from what an `analysis_result` has ever meant in this schema.
  - A concrete conflict this avoids: `analysis_result`'s own `source.client_input_ref` names
    *one* Client Input — Scenario Compare has no single such reference (each scenario has its
    own derived one), so Option A would need either a second, incompatible identity concept
    bolted onto `source`, or would need to leave `client_input_ref` meaning something different
    only inside the `scenario_compare` block than everywhere else in the same document.
- Two separate schemas — one for the request (base + scenarios + overrides), one for the result
  (per-scenario outputs + summary + deltas) — mirrors how `client_input.schema.json` and
  `analysis_result.schema.json` are already two separate schemas for two separate concerns
  (input vs. output) rather than one combined document; Scenario Compare gets the same clean
  split, at its own layer.

**Confirmed feasible: reusing `mode_a_block`/`mode_b_block`/`mode_c_block`/`bep_block` from
`analysis_result.schema.json` via `$ref` inside `scenario_compare_result.schema.json`** — each is
already a self-contained named definition requiring only `status`/`per_component`/`warnings`,
with no dependency on being nested at the top level of `analysis_result.schema.json` specifically.
JSON Schema draft-07's `$ref` can target a definition in another file by URI
(`analysis_result.schema.json#/definitions/mode_a_block`, the same referencing style this file's
own `definitions` already use internally) — the exact `$ref` resolution mechanism (relative file
path vs. registered `$id`) is an implementation-time detail, not a design question this SPEC
needs to resolve further, but the *feasibility* of the reuse itself is confirmed, not merely
assumed.

**Shape (finalized, split across two documents):**

```
scenario_compare_request:
  base_input: <a full, valid client_input — same schema, no new shape>
  baseline_scenario_id
  scenarios:
    - scenario_id
      label
      overrides:                          (section 4 — grouped canonical shape)
        components: [ {component_id, actual_price?, target_market_price?,
                        price_includes_vat?, discount_rate?}, ... ]
        cost_items: [ {item_id, amount?, rate?}, ... ]
        targets: { target_contribution_margin_rate? }
        tax: { vat_rate? }
        fx: { rate_base_per_reporting? }

scenario_compare_result:
  status                    (module_status — section 9's rollup, aggregated once more across
                              all scenarios the same way: ERROR>INCOMPLETE>OK)
  baseline_scenario_id       (echoed from the request, for a self-contained result)
  scenarios:
    - scenario_id
      label
      scenario_status        (section 9)
      results:                             (present only if STEP 3 passed — section 7)
        mode_a: <$ref mode_a_block>
        mode_b: <$ref mode_b_block>
        mode_c: <$ref mode_c_block>
        bep:    <$ref bep_block>
      summary:   <section 10's canonical fields>
      deltas:    <section 14, present only on non-baseline scenarios>
      warnings:  <section 11 — origin_module-tagged concatenation, plus a STEP-3 schema-
                  validation failure recorded here if results is absent>
  warnings: []               (request-level errors, section 15 — duplicate scenario_id, missing/
                              unresolvable baseline_scenario_id, base_input id-uniqueness
                              failures, unresolvable override targets; note these make the
                              ENTIRE request fail, so in practice a result document reporting
                              these has status=ERROR and no scenarios[] populated at all — this
                              warnings[] array is where the specific reasons are enumerated)
```

## 20. Master Note boundary

Per `MASTER_NOTE_MAPPING.md`'s own structure, Scenario Compare connects to MN07 (feasibility
checking at a specific price/quantity — the same conceptual grounding BEP already cited) and MN08
(validation/feedback — comparing alternatives is adjacent to, though not identical to,
revising a hypothesis against real data). The Master Note supports the *general idea* that
alternatives should be compared before committing to one price/cost structure — it does not
define, and this document does not claim it defines, any of: the base+override architecture, the
merge semantics, the status-rollup rule, or the delta calculation. All of those are Pricing
Harness Internal Specification, exactly the same boundary already established for every prior
mode (`dependency_rules.md` intro, MODE C's SPEC.md §16, BEP's SPEC.md §16).

## 21. Scope exclusions (v0.1)

Not in this phase (design or implementation): Scenario Compare Python code, schema changes,
tests, Excel, Dashboard, AI recommendation/ranking/scoring, a real shared-cost allocation engine,
multi-component BEP, and report generation.

## 22. Remaining open design items

Only genuinely undecided items remain — document placement (schema architecture) is now closed
(§19, Option B).

1. **Excel scenario-count ceiling**: whether 5 is the right v0.1 Excel limit, or whether it should
   be configurable per workbook build — deferred to the (not-yet-scheduled) Excel implementation
   phase.
2. **Whether a future need will require array-*structural* overrides** (adding/removing a
   component or cost item per scenario, not just changing a value) — explicitly out of v0.1 (§4),
   revisit only if a concrete scenario genuinely needs "add a new cost item" rather than "change
   an existing one's amount."
3. **Whether delta metrics should eventually cover MODE C's `allowable_direct_cost`/
   `direct_cost_gap`** in addition to the v0.1 minimum four (§14) — flagged as a candidate
   expansion, not decided now (the user's own instruction listed it as a "예시" candidate for
   discussion, not a v0.1 requirement).
4. **`break_even_quantity_delta` vs. a future `basis`-override**: if `cost_item.basis` ever
   becomes overridable (currently excluded, §4), `break_even_quantity_delta` would need an
   explicit `analysis_period_basis` equality check before subtracting two quantities — not needed
   today because no override path can currently produce two scenarios with differing bases from
   the same `base_input` (§14).

**Explicitly closed by this revision** (previously open or underspecified, now decided — kept
here for traceability): stable-ID uniqueness within `base_input` (§3, preflight request-level
check, not previously guaranteed by `client_input.schema.json`); the canonical override schema's
exact shape (§4, grouped by `components`/`cost_items`/`targets`/`tax`/`fx`, not a flat
`{path,value}` list); omitted-vs-explicit-null override semantics (§5); the STEP 1 vs. STEP 3
error-tier boundary, including moving "unresolvable override target" from scenario-level to
request-level (§7/§15); the canonical delta metric set (§14, `net_sales_ex_vat_delta` replacing
`price_delta`); the schema document architecture (§19, Option B — separate request/result
document types, not a nested `analysis_result` block); **the baseline self-delta rule (§14,
follows the source metric's own status — never an unconditional `0`/`OK` just because both
operands are the same scenario)**; **invalid-baseline-at-STEP-3 handling (§14a,
`BASELINE_SCENARIO_INVALID_FOR_DELTA`, siblings' absolute results preserved, only their deltas go
ERROR)**; and **the fixed, non-mixed delta source module per metric (§14's table — each delta
reads exactly one named field from exactly one mode, never a similarly-named MODE B/C metric)**.
