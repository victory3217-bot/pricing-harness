# MODE A — Current Price Diagnosis — SPEC

Status: **implemented** (`core/engine/modes/mode_a.py`), covered by `tests/test_mode_a.py`
(8/8 passing) and exercised end-to-end against every `core/schemas/examples/valid/*.json`
via `core/engine/generate_analysis_results.py`.

## Question answered

> At the current price, how much is actually left on one unit of this transaction?

## Inputs consumed (from Client Input)

Per `product.price_components[]` entry (one result per component — MODE A never blends
components; see "Explicitly out of scope" below):

- `actual_price`, `currency`, `price_includes_vat`
- `tax.vat_rate`
- `fx.base_currency`, `fx.reporting_currency`, `fx.rate_base_per_reporting`
- Every `costs.items[]` entry whose `applies_to_component` matches this component (directly,
  or `"shared"` with a resolvable `allocation_rule` — see below)

## Outputs — 7 metrics per component

All wrapped `{value, status, unit}` per `core/schemas/analysis_result.schema.json`:

1. `actual_price_ex_vat`
2. `direct_cost_total`
3. `gross_profit`
4. `gross_profit_rate`
5. `variable_cost_total`
6. `contribution_margin`
7. `contribution_margin_rate`

## Formulas

```
Gross Profit            = actual_price_ex_vat − direct_cost_total
Gross Profit Rate       = Gross Profit / actual_price_ex_vat
Contribution Margin     = Gross Profit − variable_cost_total
Contribution Margin Rate = Contribution Margin / actual_price_ex_vat
```

`fixed_operating_cost` items are excluded from both Gross Profit and Contribution Margin —
reserved for the future `bep` module.

## VAT rule (conditional, not blanket)

Full table in [`core/schemas/dependency_rules.md`](../../../core/schemas/dependency_rules.md#2-vat-dependency-is-conditional-not-blanket).
Summary: `price_includes_vat = false` makes `actual_price_ex_vat = actual_price` **regardless**
of `vat_rate` — a single null field does not automatically propagate unless it's actually on
the dependency path. Verified by `test_3_vat_exclusive_price_with_null_rate`.

## Cost category → metric mapping

| `cost_category` | Included in |
|---|---|
| `product_service_direct_cost` | `direct_cost_total` (→ Gross Profit) |
| `variable_selling_delivery` | `variable_cost_total` (→ Contribution Margin, on top of Gross Profit) |
| `fixed_operating_cost` | Neither. Excluded from MODE A entirely. |

Default convention: **installation cost is `variable_selling_delivery`**, not a direct product
cost, even though it's a one-time per-unit cost. A client's own cost-accounting policy may
justify reclassifying it — that's a per-engagement Client Input decision, not an engine rule.

## Rate-based cost items

A cost item may use `amount` (money) or `rate` (0–1, applied to a revenue base) — never both
meaningfully at once. `basis` selects the base:

| `basis` | Revenue base used |
|---|---|
| `rate_of_net_sales` | `actual_price_ex_vat` (net_sales_ex_vat, N) |
| `rate_of_gross_payment` | `gross_payment_incl_vat` (G) — **always `N × (1 + vat_rate)`, regardless of `price_includes_vat`** |

**Corrected rule (this section previously stated the opposite and was wrong — see
`core/schemas/dependency_rules.md` §2)**: gross payment is *not* independent of VAT status. It
is the economic total the customer actually pays, which is always net sales grossed up by VAT.
`price_includes_vat` decides which of {`actual_price_ex_vat`, `gross_payment_incl_vat`} the raw
`actual_price` field directly equals — it never makes `vat_rate` unnecessary for computing the
*other* one:

| `price_includes_vat` | `actual_price_ex_vat` needs `vat_rate`? | `gross_payment_incl_vat` needs `vat_rate`? |
|---|---|---|
| `true` | yes | no (`= actual_price` directly) |
| `false` | no (`= actual_price` directly) | yes |
| `null` | UNKNOWN regardless | UNKNOWN regardless |

Concretely: if `price_includes_vat = false` and `vat_rate = null`, `actual_price_ex_vat` is
still `OK`, but any `rate_of_gross_payment` item is `UNKNOWN` — the fee still needs the VAT rate
to gross up the net price, even though the *displayed* price didn't need it. Verified by
`test_9`–`test_13` in `tests/test_mode_a.py` (added when this was corrected). If a client's
real-world PG settlement basis genuinely differs from "gross payment = net sales grossed up by
the same VAT rate" (e.g. a fee contractually defined against a different base entirely), that
must be modeled by reclassifying the item's `basis` (e.g. to `rate_of_net_sales`), not by the
engine guessing.

## Shared cost items and `allocation_rule`

A `"shared"` item's `allocation_rule` determines its MODE A (per-component) treatment:

| `allocation_rule` | MODE A per-component behavior |
|---|---|
| `blended_only` | Excluded entirely from every component (by design — only ever appears in the not-yet-built `blended` block) |
| `by_component_revenue` / `fixed_share` | **UNKNOWN** at every component it would apply to, with a `MISSING_DEPENDENCY` warning pointing at `blended.allocation[<item_id>]` — resolving these requires the blended (whole-contract) engine, which is not implemented yet. This is a system-limitation gap, not a data gap, and is deliberately **excluded** from `meta.missing_input_paths` (which is reserved for things the client can actually go fill in). |
| `direct` (on a `"shared"` item) | **ERROR**, code `INVALID_ALLOCATION_CONFIGURATION` — `applies_to_component = "shared"` (not attributed to one component) and `allocation_rule = "direct"` (already attributed to one) are a semantic contradiction; MODE A refuses to guess and reports the affected aggregate as `ERROR` rather than using the cost as-is. Canonical rule, shared with MODE B — see `core/schemas/dependency_rules.md` section 4. (An earlier version of this document had MODE A accept this combination "as-is"; that behavior was retired for consistency across modes.) |
| missing / anything else on a `"shared"` item | Treated as `UNKNOWN`, `MISSING_DEPENDENCY` on `costs.items[<item_id>].allocation_rule` |

Note: `direct` is also a valid `allocation_rule` value on a *non-shared* item (`applies_to_component`
set to a concrete `component_id`) — there it is simply not a contradiction and the field is
effectively unused/ignored, since a non-shared item is already unambiguously scoped.

Confirmed empirically: running MODE A against `core/schemas/examples/valid/03_hybrid_hw_saas.json`
(which uses `by_component_revenue`/`fixed_share` shared items) correctly yields `gross_profit`
= `OK` but `contribution_margin` = `UNKNOWN` for both components — Gross Profit doesn't need
those items, Contribution Margin does.

## UNKNOWN propagation

Governed by `core/schemas/dependency_rules.md` §1 and §5. In short: a metric is `OK` only if
every dependency is a confirmed value (including confirmed `0`); any `null` on the path makes
it `UNKNOWN`, never silently `0`. Each non-`OK` metric carries a `warnings[]` entry naming the
exact dependency path(s) responsible — `MISSING_DEPENDENCY` at the root cause,
`DOWNSTREAM_UNKNOWN` where a metric depends on another metric that is itself unresolved.

A cost *category* with zero matching items (e.g. no `variable_selling_delivery` items assigned
to a component at all) is a confirmed `0`, not `UNKNOWN` — there's no missing data, just no
cost of that kind on this component.

## Explicitly out of scope for this SPEC

- **Blended / whole-contract view** across components — stub only (`blended.status = "NOT_IMPLEMENTED"`).
- MODE B (target price), MODE C (allowable cost), BEP — all stub blocks.
- External competitor research, AI pricing strategy, report/quotation generation, web dashboard.
- Currency combinations beyond `item.currency ∈ {fx.base_currency, fx.reporting_currency}` —
  anything else yields an `ERROR` status metric (not exercised by current tests/examples).

## Code locations

- `core/engine/modes/mode_a.py` — calculation
- `core/engine/validation/validate_client_input.py` — Client Input schema check
- `core/engine/result_builder.py` — assembles the full Analysis Result document
- `core/engine/generate_analysis_results.py` — runs the above over every example, for regression checking
- `tests/test_mode_a.py` — 8 unit tests
