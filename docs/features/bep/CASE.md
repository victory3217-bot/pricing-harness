# BEP — CASE (DRAFT v0.1)

Fictional data only (`client_id: sample_co_zeta`) — not any real client. No engine code exists
yet — every number below is hand-calculated per the formulas in `SPEC.md`, for review. All cases
use a single component named `main` unless explicitly noted (TC18/TC19 test the multi-component
refusal itself). `v = 0.10` where a VAT rate is known. `CMu` follows MODE A's Contribution Margin
semantics (SPEC.md §3): `CMu = N − direct_cost − variable_cost_total`.

---

**TC1 — simple positive CM**
`N=1000, direct_cost=400, variable_cost_total=100(fixed-amount item)` → `CMu = 1000−400−100 = 500`.
`fixed_operating_cost` item: component-scoped (`applies_to_component: "main"`), `amount=50000`,
`basis: "per_month"`.
`FC = 50000` — OK.
`Q_BEP = 50000 / 500 = 100` — **OK**, `break_even_quantity_exact = 100`.

**TC2 — fixed cost = 0 (explicit)**
Same `CMu = 500` as TC1. `fixed_operating_cost` item exists, component-scoped, `amount = 0`
(explicit, not omitted).
`FC = 0` — OK (explicit zero, not UNKNOWN, per SPEC.md §7).
`Q_BEP = 0 / 500 = 0` — **OK**, `break_even_quantity_exact = 0`. Correct answer: with no fixed
cost, the business is break-even from the first unit.

**TC3 — no fixed-cost item at all (confirmed 0, contrast with TC2)**
Same `CMu = 500`. No `fixed_operating_cost` item exists for `main` at all — not component-scoped,
not shared.
Per SPEC.md §7's no-item rule: `FC = 0`, confirmed, **OK** — numerically identical to TC2
(`Q_BEP = 0`) but pins down the "nothing to sum" branch specifically, not to be confused with
TC4's "item present, value missing."

**TC4 — fixed-cost item exists but `amount = null`**
Same `CMu = 500`. A `fixed_operating_cost` item exists, component-scoped, `amount = null`
(not yet entered).
`FC` — **UNKNOWN**, code `MISSING_DEPENDENCY`, dependency `costs.items[<item_id>].amount`.
`break_even_quantity_exact` — **UNKNOWN**, `DOWNSTREAM_UNKNOWN`, dependency
`bep.per_component.main.fixed_operating_cost`.

**TC5 — CM = 0, FC > 0 (break-even undefined, zero margin)**
`N=1000, direct_cost=600, variable_cost_total=400(fixed-amount)` → `CMu = 1000−600−400 = 0` — OK
(a valid, fully computed metric — all inputs known).
`FC = 50000` (component-scoped) — OK.
`break_even_quantity_exact` — **`{value: null, status: "NOT_APPLICABLE"}`**, non-blocking warning
`BREAK_EVEN_UNDEFINED_ZERO_MARGIN` (SPEC.md §6, revised). `module_status` stays **OK**
(`NOT_APPLICABLE` is neither ERROR nor UNKNOWN — SPEC.md §15).

**TC6 — CM < 0, FC > 0 (break-even undefined, negative margin)**
`N=1000, direct_cost=700, variable_cost_total=400(fixed-amount)` → `CMu = 1000−700−400 = −100` —
OK (fully valid, confirms the business loses more per unit sold).
`FC = 50000` (component-scoped) — OK.
`break_even_quantity_exact` — **`{value: null, status: "NOT_APPLICABLE"}`**, non-blocking warning
`BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN`. `module_status` stays **OK**.

**TC7 — VAT-inclusive display price**
`actual_price=1100, price_includes_vat=true, v=0.10` → `N = 1100/1.10 = 1000`.
`direct_cost=400`, `variable_cost_total=100` (fixed-amount, VAT-independent) → `CMu = 500`.
`FC = 50000` (component-scoped) → `Q_BEP = 100` — **OK**. Confirms display-price convention
doesn't change the economic answer (same principle established in MODE A/MODE C TC5/TC6).

**TC8 — VAT-exclusive display price, same underlying economics as TC7**
`actual_price=1000, price_includes_vat=false, v=0.10` → `N = 1000` directly.
Same `direct_cost=400`, `variable_cost_total=100` → `CMu = 500`, `FC = 50000` →
`Q_BEP = 100` — **OK**, identical to TC7.

**TC9 — variable net-sales fee (rate_of_net_sales)**
`N=1000, direct_cost=200`. One `variable_selling_delivery` item, `basis: rate_of_net_sales`,
`rate=0.1` → variable_cost_total contribution `= 0.1 × 1000 = 100`.
`CMu = 1000 − 200 − 100 = 700`. `FC = 70000` (component-scoped) → `Q_BEP = 70000/700 = 100` —
**OK**.

**TC10 — gross-payment fee (rate_of_gross_payment)**
`price_includes_vat=false, target actual_price=1000 (=N), v=0.10` → `G = 1000×1.10 = 1100`.
`direct_cost=0`. One `variable_selling_delivery` item, `basis: rate_of_gross_payment`,
`rate=0.05` → contribution `= 0.05 × 1100 = 55`.
`CMu = 1000 − 0 − 55 = 945`. `FC = 94500` (component-scoped) → `Q_BEP = 94500/945 = 100` —
**OK**. `v` was required here because a gross-payment-basis fee is present (same per-metric VAT
dependency already established for MODE A/B/C).

**TC11 — VAT UNKNOWN but not actually needed (a=0, price_includes_vat=false)**
`actual_price=1000, price_includes_vat=false, v=null`. No `rate_of_gross_payment` item exists (so
`G` is never referenced). One `rate_of_net_sales` item, `rate=0.1`.
`N = 1000` directly (doesn't need `v`, since `price_includes_vat=false`).
`direct_cost=300`, `variable_cost_total = 0.1×1000 = 100` → `CMu = 1000−300−100 = 600`.
`FC = 60000` (component-scoped) → `Q_BEP = 100` — **OK**, despite `v` being null. Mirrors MODE
C's TC7/TC8 lesson: "is `v` known" is the wrong question; "is a gross-payment-basis fee present"
is the right one.

**TC12 — VAT UNKNOWN and actually required**
`actual_price=1100, price_includes_vat=true, v=null` → `N` cannot be computed (needs `v` to
convert from the VAT-inclusive display price).
`market... ` *(N/A — not MODE C; this is MODE A-style `actual_price_ex_vat`)* — `N` —
**UNKNOWN**, `MISSING_DEPENDENCY`, dependency `tax.vat_rate`.
`contribution_margin_per_unit` — **UNKNOWN**, `DOWNSTREAM_UNKNOWN` (needs `N`).
`break_even_quantity_exact` — **UNKNOWN**, `DOWNSTREAM_UNKNOWN` (needs `contribution_margin_per_unit`),
regardless of `fixed_operating_cost`'s own status.

**TC13 — unsupported currency on the fixed-cost item**
Same `CMu = 500` as TC1 (`N=1000, direct_cost=400, variable_cost_total=100`).
`fixed_operating_cost` item: component-scoped, `amount=50000`, `currency="EUR"` — but
`fx.base_currency = fx.reporting_currency = "KRW"` (no EUR conversion path configured, same
`convert_to_reporting()` behavior already exercised by MODE A/B/C's unsupported-currency cases).
`FC` — **ERROR** (unsupported currency, via `convert_to_reporting()`'s existing ERROR path — no
new currency rule per SPEC.md §13).
`break_even_quantity_exact` — **ERROR**, `DOWNSTREAM_ERROR`.

**TC14 — shared fixed cost, unresolved allocation**
Same `CMu = 500` as TC1. `fixed_operating_cost` item: `applies_to_component: "shared"`,
`allocation_rule: "by_component_revenue"` (not yet resolvable — needs the not-yet-built blended
engine).
`FC` — **UNKNOWN**, code `UNSUPPORTED_SHARED_COST_ALLOCATION`, dependency
`blended.allocation[<item_id>]` (canonical rule, unchanged — this is the *non*-`blended_only`
shared branch).
`break_even_quantity_exact` — **UNKNOWN**, `DOWNSTREAM_UNKNOWN`.

**TC15 — shared + direct invalid configuration**
Same `CMu = 500`. `fixed_operating_cost` item: `applies_to_component: "shared"`,
`allocation_rule: "direct"` (semantic contradiction).
`FC` — **ERROR**, code `INVALID_ALLOCATION_CONFIGURATION`, dependency
`costs.items[<item_id>].allocation_rule` (canonical rule, unchanged).
`break_even_quantity_exact` — **ERROR**, `DOWNSTREAM_ERROR`.

**TC16 — explicit zero rate does not block computation**
`N=1000, direct_cost=400`. One `rate_of_net_sales` item, `rate=0` (explicit, not omitted).
`variable_cost_total = 0×1000 = 0` → `CMu = 1000−400−0 = 600`.
`FC = 60000` (component-scoped) → `Q_BEP = 100` — **OK**. Confirms `rate=0` (explicit) behaves
identically to "no rate-basis item at all," not as UNKNOWN — same principle as MODE B/C's
explicit-zero cases.

**TC17 — non-integer break-even quantity**
`N=1000, direct_cost=400, variable_cost_total=100(fixed-amount)` → `CMu = 500` (same as TC1).
`FC = 52340` (component-scoped, `basis: per_month`).
`Q_BEP = 52340 / 500 = 104.68` — **OK**, `break_even_quantity_exact = 104.68` (never rounded,
SPEC.md §8). No `break_even_quantity_units` metric is produced in v0.1 at all — SPEC.md §8
(revised) excludes it entirely (the earlier `type`-based rounding proxy was rejected); any
rounding for a specific client context (e.g. displaying "105 units needed") is a presentation-
layer decision outside the engine.

**TC18 — multi-component input, component-specific fixed costs (BEP v0.1 refuses — ERROR)**
Two components: `main` (as TC1: `CMu=500`, component-scoped `FC=50000`) and `addon` (a second
component with its own component-scoped `FC=20000` and its own CM). Even though *both* fixed
costs here are cleanly component-scoped (no shared-cost ambiguity at all in this particular
input), **BEP v0.1 does not compute anything** — SPEC.md §11 restricts BEP v0.1 to exactly one
`price_components[]` entry, unconditionally.
Result: `run_bep(client_input)` returns `status = "ERROR"`, `per_component = {}` (no per-
component `Q_BEP` numbers produced for either `main` or `addon`, not even partially), one
warning: `code = "MULTI_COMPONENT_BEP_NOT_SUPPORTED"`, `metric_path = "bep"`,
`dependency_paths = ["product.price_components"]` (finalized mechanism, SPEC.md §11/§18). This
deliberately shows the restriction applies even in the *easiest possible* multi-component case,
to make clear it is a v0.1 scope boundary, not a workaround for a harder case only.

**TC19 — multi-component input, with a shared fixed cost (motivating case for the restriction)**
Same two components as TC18, but a *third* `fixed_operating_cost` item is added:
`applies_to_component: "shared"`, `allocation_rule: "blended_only"`, `amount=8000000`,
covering both components together. This is the exact real-world pattern SPEC.md §4/§11 found in
all four existing example Client Inputs. A naive per-component `FC_i / CMu_i` (ignoring the
restriction) would either double-count this shared `8000000` against both `main` and `addon`, or
(if "excluded" is applied per the old A/B/C rule) silently drop it to zero for both — both wrong.
BEP v0.1's actual behavior is identical to TC18: `status = "ERROR"`, `per_component = {}`,
`MULTI_COMPONENT_BEP_NOT_SUPPORTED`. This case exists specifically to document *why* the
restriction exists, not to produce a different outcome than TC18.

**TC21 — FC = 0, CM = 0 (both terms simultaneously zero — distinct warning)**
`N=1000, direct_cost=600, variable_cost_total=400(fixed-amount)` → `CMu = 0` — OK.
`fixed_operating_cost` item exists, component-scoped, `amount = 0` (explicit) → `FC = 0` — OK.
`break_even_quantity_exact` — **`{value: null, status: "NOT_APPLICABLE"}`**, warning
`BREAK_EVEN_UNDEFINED_ZERO_MARGIN_ZERO_FIXED_COST` (SPEC.md §9's matrix — distinct code from TC5,
since raw `FC/CMu` here is `0/0`, an indeterminate form, not "real fixed cost, zero margin").

**TC22 — FC = 0, CM < 0 (raw arithmetic gives 0, must still be NOT_APPLICABLE)**
`N=1000, direct_cost=700, variable_cost_total=400(fixed-amount)` → `CMu = −100` — OK.
`fixed_operating_cost` item exists, component-scoped, `amount = 0` (explicit) → `FC = 0` — OK.
Raw division `0 / −100 = 0` is mathematically well-defined, but SPEC.md §6/§9 explicitly forbids
reporting it: `break_even_quantity_exact` — **`{value: null, status: "NOT_APPLICABLE"}`**, warning
`BREAK_EVEN_UNDEFINED_NEGATIVE_MARGIN` (same code as TC6 — FC's value does not change the
diagnosis once CMu<0). This case exists specifically to pin down that the engine must not
special-case "well, the math gives exactly 0" into reporting `0` — the override is unconditional
whenever CMu<0.

**TC23 — negative fixed_operating_cost amount (new rule, SPEC.md §4)**
Same `CMu = 500` as TC1 (`N=1000, direct_cost=400, variable_cost_total=100`).
`fixed_operating_cost` item: component-scoped, `amount = −10000` (entered negative, e.g. a
mis-keyed refund/credit).
`fixed_operating_cost` — **ERROR**, code `INVALID_NEGATIVE_COST`, dependency
`costs.items[<item_id>].amount`.
`break_even_quantity_exact` — **ERROR**, `DOWNSTREAM_ERROR`.

**TC20 — Contribution Margin input UNKNOWN (direct cost missing)**
`N=1000` (known). `product_service_direct_cost` item exists, component-scoped, `amount=null`
(not yet entered). `variable_cost_total=100` (fixed-amount, known).
`contribution_margin_per_unit` — **UNKNOWN**, `MISSING_DEPENDENCY`, dependency
`costs.items[<item_id>].amount`.
`fixed_operating_cost` — separately, `FC=50000` (component-scoped) — **OK**, completely
unaffected (same dependency-isolation discipline as MODE C §9: a problem on one input must not
corrupt an unrelated one that happens to still be fully known).
`break_even_quantity_exact` — **UNKNOWN**, `DOWNSTREAM_UNKNOWN`, dependency
`bep.per_component.main.contribution_margin_per_unit` — even though `FC` itself is OK, BEP cannot
produce a quantity without a known per-unit margin.

---

## Summary table

| TC | Scenario | CMu | FC | `break_even_quantity_exact` | Status |
|---|---|---|---|---|---|
| 1 | simple positive CM | 500 | 50000 | 100 | OK |
| 2 | fixed cost = 0 (explicit) | 500 | 0 | 0 | OK |
| 3 | no fixed-cost item at all | 500 | 0 (confirmed) | 0 | OK |
| 4 | fixed-cost item, amount null | 500 | — | — | UNKNOWN |
| 5 | CM = 0, FC > 0 | 0 | 50000 | null | NOT_APPLICABLE + warning |
| 6 | CM < 0, FC > 0 | −100 | 50000 | null | NOT_APPLICABLE + warning |
| 7 | VAT-inclusive display | 500 | 50000 | 100 | OK |
| 8 | VAT-exclusive display, same economics | 500 | 50000 | 100 | OK |
| 9 | net-sales fee | 700 | 70000 | 100 | OK |
| 10 | gross-payment fee | 945 | 94500 | 100 | OK |
| 11 | v UNKNOWN, not needed | 600 | 60000 | 100 | OK |
| 12 | v UNKNOWN, needed | — | n/a | — | UNKNOWN |
| 13 | unsupported currency (FC item) | 500 | — | — | ERROR |
| 14 | shared FC, unresolved | 500 | — | — | UNKNOWN |
| 15 | shared FC, invalid (shared+direct) | 500 | — | — | ERROR |
| 16 | explicit zero rate | 600 | 60000 | 100 | OK |
| 17 | non-integer quantity | 500 | 52340 | 104.68 (no `_units` metric in v0.1) | OK |
| 18 | multi-component, component-specific FC | — | — | `per_component={}` | ERROR (`MULTI_COMPONENT_BEP_NOT_SUPPORTED`) |
| 19 | multi-component + shared FC | — | — | `per_component={}` | ERROR (`MULTI_COMPONENT_BEP_NOT_SUPPORTED`) |
| 20 | CM input UNKNOWN | — | 50000 (OK, isolated) | — | UNKNOWN |
| 21 | FC = 0, CM = 0 | 0 | 0 | null | NOT_APPLICABLE + warning (`_ZERO_FIXED_COST`) |
| 22 | FC = 0, CM < 0 | −100 | 0 | null (never `0`) | NOT_APPLICABLE + warning |
| 23 | negative fixed-cost amount | 500 | — | — | ERROR (`INVALID_NEGATIVE_COST`) |
